import {
  AccountDisabledError,
  AccountNotFoundError,
  AutomationActionSchema,
  createId,
  JobNotCancellableError,
  JobNotFoundError,
  JobNotRetryableError,
  nowIso,
  type CreateJobBatchInput,
  type CreateJobInput,
  type Job,
  type QueueStats,
} from '@fb/shared';
import { isCancellable, isRetriable, jobTypeOf, type JobFilter, type Page } from '@fb/domain';
import type { EventPublisher } from '../ports/EventPublisher.js';
import type { Logger } from '../ports/Logger.js';
import type { QueuePort } from '../ports/Queue.js';
import type { Repositories } from '../ports/Repositories.js';

export interface JobServiceDeps {
  repositories: Repositories;
  queue: QueuePort;
  events: EventPublisher;
  logger: Logger;
}

/**
 * Creating a job is a database write, not a start signal. The queue is only
 * nudged afterwards, so a job that is accepted is already durable and a crash
 * one millisecond later loses nothing.
 */
export class JobService {
  constructor(private readonly deps: JobServiceDeps) {}

  async create(input: CreateJobInput): Promise<Job> {
    const [job] = await this.createMany([input.accountId], input);
    if (job === undefined) throw new JobNotFoundError('unknown');
    return job;
  }

  /** Compose sends one action to several accounts; each gets its own job. */
  async createBatch(input: CreateJobBatchInput): Promise<Job[]> {
    return this.createMany(input.accountIds, input);
  }

  async get(id: string): Promise<Job> {
    const job = await this.deps.repositories.jobs.findById(id);
    if (job === null) throw new JobNotFoundError(id);
    return job;
  }

  async list(filter: JobFilter): Promise<Page<Job>> {
    return this.deps.repositories.jobs.list(filter);
  }

  async stats(): Promise<QueueStats> {
    return this.deps.repositories.jobs.stats();
  }

  /**
   * Cancels a job wherever it is. A running job is aborted through the queue
   * and writes its own final state; anything else is written here.
   */
  async cancel(id: string): Promise<Job> {
    const job = await this.get(id);
    if (!isCancellable(job.status)) throw new JobNotCancellableError(id, job.status);

    if (job.status === 'running' && this.deps.queue.requestCancel(id)) {
      this.deps.logger.info('Cancellation requested for a running job', {
        event: 'job.cancel_requested',
        jobId: id,
        accountId: job.accountId,
      });
      return job;
    }

    const cancelled = await this.deps.repositories.jobs.update(id, {
      status: 'cancelled',
      finishedAt: nowIso(),
    });

    this.deps.events.publish({ type: 'job.cancelled', timestamp: nowIso(), payload: cancelled });
    return cancelled;
  }

  /** Sends a finished, unsuccessful job round again with a fresh attempt budget. */
  async retry(id: string): Promise<Job> {
    const job = await this.get(id);
    if (!isRetriable(job.status)) throw new JobNotRetryableError(id, job.status);

    const account = await this.deps.repositories.accounts.findById(job.accountId);
    if (account === null) throw new AccountNotFoundError(job.accountId);
    if (!account.enabled) throw new AccountDisabledError(job.accountId);

    const retried = await this.deps.repositories.jobs.update(id, {
      status: 'pending',
      retryCount: 0,
      progress: 0,
      runAfter: null,
      result: null,
      lastError: null,
      queuedAt: null,
      startedAt: null,
      finishedAt: null,
    });

    this.deps.events.publish({ type: 'job.created', timestamp: nowIso(), payload: retried });
    this.deps.queue.notify();
    return retried;
  }

  private async createMany(
    accountIds: readonly string[],
    input: Omit<CreateJobBatchInput, 'accountIds'>,
  ): Promise<Job[]> {
    const { repositories, events, queue } = this.deps;
    const settings = await repositories.settings.read();

    // Every account is checked before anything is written, so a batch either
    // goes in whole or not at all.
    for (const accountId of accountIds) {
      const account = await repositories.accounts.findById(accountId);
      if (account === null) throw new AccountNotFoundError(accountId);
      if (!account.enabled) throw new AccountDisabledError(accountId);
    }

    // Parsed rather than trusted: the caller may hand us the input shape, where
    // fields with defaults are still optional.
    const action = AutomationActionSchema.parse(input.action);
    const created = await repositories.jobs.createMany(
      accountIds.map((accountId) => ({
        id: createId('job'),
        accountId,
        type: jobTypeOf(action),
        payload: action,
        priority: input.priority ?? 0,
        maxRetries: input.maxRetries ?? settings.defaultMaxRetries,
        status: 'pending' as const,
        runAfter: input.scheduledFor ?? null,
      })),
    );

    for (const job of created) {
      events.publish({ type: 'job.created', timestamp: nowIso(), payload: job });
    }

    queue.notify();
    return created;
  }
}
