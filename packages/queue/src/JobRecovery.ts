import { nowIso } from '@fb/shared';
import type { Logger, Repositories } from '@fb/application';

export interface RecoveryReport {
  requeued: string[];
  needsAttention: string[];
}

export interface JobRecoveryDeps {
  repositories: Repositories;
  logger: Logger;
}

const INTERRUPTED_MESSAGE =
  'The server stopped while this job was running. It may have partly completed, so it was not repeated automatically.';

/**
 * Puts the queue back together after a restart, and keeps it honest while it
 * runs.
 *
 * At startup every `queued` or `running` row is abandoned by definition: the
 * process that claimed them is gone and this one holds none of them. What to
 * do with each depends on whether it had started. A `queued` job was claimed
 * but never acted on, so it can go straight back. A `running` job may already
 * have had an effect — the post may be live — and re-running it would post
 * twice, so it is failed and offered to the operator for a deliberate retry.
 * They are the only party who can tell whether it landed.
 */
export class JobRecovery {
  constructor(private readonly deps: JobRecoveryDeps) {}

  async recover(): Promise<RecoveryReport> {
    const { repositories, logger } = this.deps;
    const abandoned = await repositories.jobs.findByStatus(['queued', 'running']);
    const report: RecoveryReport = { requeued: [], needsAttention: [] };

    for (const job of abandoned) {
      if (job.status === 'queued') {
        await repositories.jobs.update(job.id, {
          status: 'pending',
          queuedAt: null,
          startedAt: null,
          // No backoff: the outage has already served as the delay.
          runAfter: null,
        });
        report.requeued.push(job.id);
        continue;
      }

      await this.markInterrupted(job.id);
      report.needsAttention.push(job.id);
    }

    if (report.requeued.length + report.needsAttention.length > 0) {
      logger.warn(
        `Recovered ${report.requeued.length} queued job(s); ${report.needsAttention.length} interrupted job(s) need a decision`,
        { event: 'queue.recovered' },
      );
    }

    return report;
  }

  /**
   * Catches jobs that are marked running but have no worker behind them while
   * the server is up — a processor that died without recording an outcome.
   * Anything this worker is actually running is left alone.
   */
  async sweepOrphans(
    staleAfterMs: number,
    activeJobIds: readonly string[],
    now: Date = new Date(),
  ): Promise<string[]> {
    const cutoff = new Date(now.getTime() - staleAfterMs);
    const candidates = await this.deps.repositories.jobs.findStaleRunning(cutoff);
    const active = new Set(activeJobIds);

    const orphans = candidates.filter(
      (job) => job.status === 'running' && !active.has(job.id) && job.startedAt !== null,
    );

    for (const job of orphans) await this.markInterrupted(job.id);

    if (orphans.length > 0) {
      this.deps.logger.warn(`Gave up on ${orphans.length} orphaned job(s)`, {
        event: 'queue.orphans_swept',
      });
    }

    return orphans.map((job) => job.id);
  }

  private async markInterrupted(jobId: string): Promise<void> {
    await this.deps.repositories.jobs.update(jobId, {
      status: 'failed',
      finishedAt: nowIso(),
      lastError: {
        code: 'INTERNAL_ERROR',
        message: INTERRUPTED_MESSAGE,
        // Retryable so the operator can send it round again from the Queue
        // page once they have checked.
        retryable: true,
        occurredAt: nowIso(),
      },
    });
  }
}
