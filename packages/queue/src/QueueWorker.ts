import { nowIso, type Job, type JobType } from '@fb/shared';
import type { EventPublisher, Logger, Repositories } from '@fb/application';
import type { AccountLockManager } from './AccountLockManager.js';
import type { JobProcessor } from './JobProcessor.js';

export interface QueueWorkerDeps {
  repositories: Repositories;
  processor: JobProcessor;
  accountLocks: AccountLockManager;
  events: EventPublisher;
  logger: Logger;
  concurrency: () => number;
  /** Watch-live jobs allowed at once; zero means no cap. */
  liveViewers: () => number;
}

/** How many watch-live jobs one pass claims when the lane has no cap. */
const LIVE_LANE_BATCH = 500;

interface Lane {
  limit: number;
  types?: readonly JobType[];
  excludeTypes?: readonly JobType[];
}

interface RunningJob {
  job: Job;
  controller: AbortController;
}

/**
 * The loop that turns stored rows into running work.
 *
 * It never holds a job in memory as the source of truth: it claims rows, runs
 * them, and writes the outcome back. Stopping the process mid-flight therefore
 * loses nothing that recovery cannot reconstruct.
 */
export class QueueWorker {
  private readonly running = new Map<string, RunningJob>();
  private pumping = false;
  private pumpAgain = false;

  constructor(private readonly deps: QueueWorkerDeps) {}

  /**
   * Claims and starts as much work as there is room for. Re-entrant calls are
   * collapsed into one more pass, so a burst of `notify()` cannot start the
   * same job twice.
   */
  async pump(): Promise<void> {
    if (this.pumping) {
      this.pumpAgain = true;
      return;
    }

    this.pumping = true;
    try {
      do {
        this.pumpAgain = false;
        await this.claimAndStart();
      } while (this.pumpAgain);
    } finally {
      this.pumping = false;
    }
  }

  /**
   * Two lanes. A live is only watched when many accounts watch it together,
   * so watch-live jobs are claimed first against their own cap (zero meaning
   * none) and never count against the global limit, which covers the rest.
   */
  private async claimAndStart(): Promise<void> {
    const liveRunning = (): number =>
      [...this.running.values()].filter((entry) => entry.job.type === 'watch_live').length;

    const liveLimit = this.deps.liveViewers();
    const freeLive = liveLimit === 0 ? LIVE_LANE_BATCH : liveLimit - liveRunning();
    if (freeLive > 0) {
      await this.claim({ limit: Math.min(freeLive, LIVE_LANE_BATCH), types: ['watch_live'] });
    }

    const freeOther = this.deps.concurrency() - (this.running.size - liveRunning());
    if (freeOther > 0) await this.claim({ limit: freeOther, excludeTypes: ['watch_live'] });
  }

  private async claim(lane: Lane): Promise<void> {
    const claimed = await this.deps.repositories.jobs.claimDueJobs({
      busyAccountIds: this.deps.accountLocks.heldAccountIds(),
      now: new Date(),
      ...lane,
    });

    for (const job of claimed) {
      // The account lock is taken in memory before the job leaves this loop:
      // the claim query only knows about accounts that were already busy when
      // it ran.
      if (!this.deps.accountLocks.tryAcquire(job.accountId, job.id)) {
        await this.deps.repositories.jobs.update(job.id, { status: 'pending', queuedAt: null });
        continue;
      }

      this.start(job);
    }
  }

  private start(job: Job): void {
    const controller = new AbortController();
    this.running.set(job.id, { job, controller });

    void this.deps.processor
      .run(job, controller.signal)
      .catch((error: unknown) => {
        // The processor writes its own outcome; reaching here means even that
        // failed, so the job is left for recovery rather than lost silently.
        this.deps.logger.error('A job ended without recording an outcome', {
          event: 'queue.processor_failed',
          jobId: job.id,
          accountId: job.accountId,
          reason: error instanceof Error ? error.message : String(error),
        });
      })
      .finally(() => {
        this.running.delete(job.id);
        this.deps.accountLocks.release(job.accountId);
        this.publishStats();
        // A finished job frees a slot, so look for more work immediately.
        void this.pump();
      });
  }

  /** Aborts a running job. False when this worker is not running it. */
  requestCancel(jobId: string): boolean {
    const running = this.running.get(jobId);
    if (running === undefined) return false;
    running.controller.abort();
    return true;
  }

  runningJobs(): Job[] {
    return [...this.running.values()].map((entry) => entry.job);
  }

  capacity(): { busy: number; limit: number } {
    return { busy: this.running.size, limit: this.deps.concurrency() };
  }

  /** Waits for what is already running, without claiming anything new. */
  async drain(timeoutMs: number): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (this.running.size > 0 && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }

    for (const running of this.running.values()) running.controller.abort();
  }

  private publishStats(): void {
    void this.deps.repositories.jobs
      .stats()
      .then((stats) => {
        this.deps.events.publish({ type: 'queue.stats', timestamp: nowIso(), payload: stats });
      })
      .catch(() => {
        // Statistics are a convenience; failing to publish them changes nothing.
      });
  }
}
