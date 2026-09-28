import { JobCancelledError, nowIso, type Job, type JobError } from '@fb/shared';
import { classifyError, type AutomationGateway } from '@fb/domain';
import type { BrowserService, EventPublisher, Logger, Repositories } from '@fb/application';
import type { RetryManager } from './RetryManager.js';

export interface JobProcessorDeps {
  repositories: Repositories;
  gateway: AutomationGateway;
  browsers: BrowserService;
  retries: RetryManager;
  events: EventPublisher;
  logger: Logger;
}

export interface JobOutcome {
  job: Job;
  status: 'completed' | 'failed' | 'retrying' | 'cancelled';
}

/**
 * Runs exactly one job from `queued` to a terminal state.
 *
 * It owns the whole of one attempt: making sure a browser is there, marking
 * the account busy, handing the action to the gateway, and writing down what
 * happened. Deciding *which* job runs, and how many at once, belongs to the
 * worker above it.
 */
export class JobProcessor {
  constructor(private readonly deps: JobProcessorDeps) {}

  async run(claimed: Job, signal: AbortSignal): Promise<JobOutcome> {
    const { repositories, events, logger } = this.deps;
    const log = logger.child({ jobId: claimed.id, accountId: claimed.accountId });

    if (signal.aborted) return this.cancel(claimed, 'Cancelled before it started');

    const settings = await repositories.settings.read();
    const started = await repositories.jobs.update(claimed.id, {
      status: 'running',
      startedAt: nowIso(),
      progress: 0,
    });

    log.info('Job started', { event: 'job.started', type: started.type });
    events.publish({ type: 'job.started', timestamp: nowIso(), payload: started });

    const startedAtMs = Date.now();

    try {
      // A job needs a browser. Starting one here — rather than refusing —
      // means a queued job survives an operator having closed the window.
      const session = await this.ensureBrowser(started.accountId);
      await this.setAccountStatus(started.accountId, 'busy');

      const result = await this.deps.gateway.execute(started.payload, {
        jobId: started.id,
        accountId: started.accountId,
        sessionId: session.sessionId,
        signal,
        timeoutMs: settings.defaultTimeoutMs,
        delayRangeMs: [settings.minActionDelayMs, settings.maxActionDelayMs],
        onProgress: (progress, step) => {
          void this.reportProgress(started, progress, step);
        },
      });

      const completed = await repositories.jobs.update(started.id, {
        status: 'completed',
        progress: 100,
        result,
        finishedAt: nowIso(),
        lastError: null,
      });

      log.info('Job completed', {
        event: 'job.completed',
        durationMs: Date.now() - startedAtMs,
      });
      events.publish({ type: 'job.completed', timestamp: nowIso(), payload: completed });

      return { job: completed, status: 'completed' };
    } catch (error) {
      return this.handleFailure(started, error, signal);
    } finally {
      // The account goes back to idle whatever happened, so one bad job does
      // not leave an account looking busy for ever.
      await this.setAccountStatus(started.accountId, 'online');
    }
  }

  private async handleFailure(job: Job, error: unknown, signal: AbortSignal): Promise<JobOutcome> {
    const { repositories, retries, events, logger } = this.deps;
    const log = logger.child({ jobId: job.id, accountId: job.accountId });

    if (signal.aborted || error instanceof JobCancelledError) {
      return this.cancel(job, 'Cancelled while running');
    }

    const jobError: JobError = classifyError(error);
    const decision = retries.decide(job, jobError);

    if (decision.retry && decision.nextAttemptAt !== null) {
      const retrying = await repositories.jobs.update(job.id, {
        status: 'retrying',
        retryCount: job.retryCount + 1,
        runAfter: decision.nextAttemptAt.toISOString(),
        lastError: jobError,
        startedAt: null,
      });

      log.warn(`Job failed, retrying: ${jobError.message}`, {
        event: 'job.retrying',
        code: jobError.code,
        retryCount: retrying.retryCount,
      });

      events.publish({
        type: 'job.retrying',
        timestamp: nowIso(),
        payload: {
          jobId: retrying.id,
          accountId: retrying.accountId,
          retryCount: retrying.retryCount,
          maxRetries: retrying.maxRetries,
          nextAttemptAt: decision.nextAttemptAt.toISOString(),
        },
      });

      return { job: retrying, status: 'retrying' };
    }

    const failed = await repositories.jobs.update(job.id, {
      status: 'failed',
      lastError: jobError,
      finishedAt: nowIso(),
    });

    log.error(`Job failed: ${jobError.message}`, {
      event: 'job.failed',
      code: jobError.code,
      reason: decision.reason,
    });
    events.publish({ type: 'job.failed', timestamp: nowIso(), payload: failed });

    return { job: failed, status: 'failed' };
  }

  private async cancel(job: Job, reason: string): Promise<JobOutcome> {
    const cancelled = await this.deps.repositories.jobs.update(job.id, {
      status: 'cancelled',
      finishedAt: nowIso(),
      lastError: {
        code: 'JOB_CANCELLED',
        message: reason,
        retryable: false,
        occurredAt: nowIso(),
      },
    });

    this.deps.logger.info('Job cancelled', {
      event: 'job.cancelled',
      jobId: job.id,
      accountId: job.accountId,
    });
    this.deps.events.publish({ type: 'job.cancelled', timestamp: nowIso(), payload: cancelled });

    return { job: cancelled, status: 'cancelled' };
  }

  private async ensureBrowser(accountId: string) {
    const existing = this.deps.browsers.get(accountId);
    if (existing !== null) return existing;
    return this.deps.browsers.start(accountId);
  }

  private async reportProgress(job: Job, progress: number, step: string): Promise<void> {
    const bounded = Math.max(0, Math.min(100, progress));
    this.deps.events.publish({
      type: 'job.progress',
      timestamp: nowIso(),
      payload: { jobId: job.id, accountId: job.accountId, progress: bounded, step },
    });

    // Progress is written so a restart can show how far a job had got; a
    // failed write must never abort the job itself.
    try {
      await this.deps.repositories.jobs.update(job.id, { progress: bounded });
    } catch {
      // The event already went out; the stored value catching up is optional.
    }
  }

  private async setAccountStatus(accountId: string, status: 'busy' | 'online'): Promise<void> {
    const account = await this.deps.repositories.accounts.findById(accountId);
    // Only a running browser can be busy; if it went away, leave the status
    // the browser service set.
    if (account === null) return;
    if (status === 'busy' && account.status !== 'online') return;
    if (status === 'online' && account.status !== 'busy') return;

    const updated = await this.deps.repositories.accounts.update(accountId, { status });
    this.deps.events.publish({
      type: 'account.status.changed',
      timestamp: nowIso(),
      payload: {
        accountId,
        status: updated.status,
        previousStatus: account.status,
        reason: null,
      },
    });
  }
}
