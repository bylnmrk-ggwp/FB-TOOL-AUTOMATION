import { nowIso, type Job } from '@fb/shared';
import type { AutomationGateway } from '@fb/domain';
import type {
  AccountService,
  BrowserService,
  EventPublisher,
  GroupService,
  Logger,
  OperatorInputService,
  QueuePort,
  Repositories,
} from '@fb/application';
import { AccountLockManager } from './AccountLockManager.js';
import { JobProcessor } from './JobProcessor.js';
import { JobRecovery } from './JobRecovery.js';
import { QueueWorker } from './QueueWorker.js';
import { RetryManager } from './RetryManager.js';

export interface QueueManagerDeps {
  repositories: Repositories;
  gateway: AutomationGateway;
  browsers: BrowserService;
  accounts: AccountService;
  groups: GroupService;
  operator: OperatorInputService;
  events: EventPublisher;
  logger: Logger;
  /** How often to look for work that became due while nothing happened. */
  pollIntervalMs?: number;
}

/**
 * Owns the running queue: recovery at startup, a worker loop, and the handful
 * of things the HTTP layer is allowed to ask of it.
 *
 * A poll timer runs alongside `notify()` because some work becomes due without
 * anybody asking — a retry backoff expiring, or a job scheduled for later.
 */
export class QueueManager implements QueuePort {
  private readonly accountLocks = new AccountLockManager();
  private readonly retries = new RetryManager();
  private readonly worker: QueueWorker;
  private readonly recovery: JobRecovery;
  private timer: NodeJS.Timeout | null = null;
  private concurrencyLimit = 1;
  private running = false;

  constructor(private readonly deps: QueueManagerDeps) {
    const processor = new JobProcessor({
      repositories: deps.repositories,
      gateway: deps.gateway,
      browsers: deps.browsers,
      accounts: deps.accounts,
      groups: deps.groups,
      operator: deps.operator,
      retries: this.retries,
      events: deps.events,
      logger: deps.logger,
    });

    this.worker = new QueueWorker({
      repositories: deps.repositories,
      processor,
      accountLocks: this.accountLocks,
      events: deps.events,
      logger: deps.logger,
      concurrency: () => this.concurrencyLimit,
    });

    this.recovery = new JobRecovery({ repositories: deps.repositories, logger: deps.logger });
  }

  /** Recovers abandoned work, then starts accepting new work. */
  async start(): Promise<void> {
    if (this.running) return;

    const settings = await this.deps.repositories.settings.read();
    this.concurrencyLimit = settings.globalConcurrency;

    await this.recovery.recover();

    this.running = true;
    this.timer = setInterval(() => {
      void this.tick();
    }, this.deps.pollIntervalMs ?? 1_000);
    // Node should not stay alive purely because the queue is idling.
    this.timer.unref();

    this.deps.logger.info(`Queue started with a limit of ${this.concurrencyLimit} job(s)`, {
      event: 'queue.started',
    });

    void this.worker.pump();
  }

  async stop(drainTimeoutMs = 10_000): Promise<void> {
    if (!this.running) return;
    this.running = false;

    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;

    await this.worker.drain(drainTimeoutMs);
    this.deps.logger.info('Queue stopped', { event: 'queue.stopped' });
  }

  isRunning(): boolean {
    return this.running;
  }

  notify(): void {
    if (!this.running) return;
    void this.worker.pump();
  }

  requestCancel(jobId: string): boolean {
    return this.worker.requestCancel(jobId);
  }

  runningJobs(): readonly Job[] {
    return this.worker.runningJobs();
  }

  capacity(): { busy: number; limit: number } {
    return this.worker.capacity();
  }

  /** Applied on the next pass, so a change on the Settings page takes hold. */
  setConcurrency(limit: number): void {
    this.concurrencyLimit = Math.max(1, limit);
    this.notify();
  }

  private async tick(): Promise<void> {
    try {
      // Settings can change while the server runs; re-reading here is cheap
      // and keeps the limit honest without a restart.
      const settings = await this.deps.repositories.settings.read();
      this.concurrencyLimit = settings.globalConcurrency;

      // A processor can die without recording anything; this is the only way
      // such a job is ever noticed while the server stays up.
      await this.recovery.sweepOrphans(
        settings.staleJobTimeoutMs,
        this.worker.runningJobs().map((job) => job.id),
      );

      await this.worker.pump();
    } catch (error) {
      this.deps.logger.error('The queue tick failed', {
        event: 'queue.tick_failed',
        reason: error instanceof Error ? error.message : String(error),
        timestamp: nowIso(),
      });
    }
  }
}
