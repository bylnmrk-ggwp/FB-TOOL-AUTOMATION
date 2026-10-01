import {
  AccountDisabledError,
  AccountNotFoundError,
  AutomationActionSchema,
  createId,
  JobNotCancellableError,
  JobNotFoundError,
  JobNotRetryableError,
  nowIso,
  type AutomationAction,
  type ActivityKind,
  type AutomationActionInput,
  type CreateJobBatchInput,
  type CreateJobInput,
  type Job,
  type QueueStats,
  type ReactionType,
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

export interface ShareToGroupsRequest {
  accountIds: readonly string[];
  postUrl: string;
  groups: ReadonlyArray<{ name: string; url: string | null }>;
  comments: readonly string[];
  reaction: ReactionType | null;
  /** Also share to each account's own timeline and story before the first group. */
  shareToTimeline: boolean;
  /** Leave out groups an account has already shared this post to. */
  skipDone: boolean;
  priority?: number;
}

export interface CommentPostRequest {
  accountIds: readonly string[];
  postUrl: string;
  /** One comment per account, in order; the list repeats when accounts outnumber it. */
  comments: readonly string[];
  /** What follows the comment on the same post. */
  then: 'none' | 'react' | 'timeline' | 'story';
  reaction: ReactionType | null;
  /** Leave out what an account has already done to this post. */
  skipDone: boolean;
  priority?: number;
  scheduledFor?: string;
}

export interface JoinGroupsRequest {
  accountIds: readonly string[];
  groupUrls: readonly string[];
  skipDone: boolean;
  priority?: number;
}

interface CreateOptions {
  priority?: number;
  maxRetries?: number;
  scheduledFor?: string;
}

/**
 * Creating a job is a database write, not a start signal. The queue is only
 * nudged afterwards, so a job that is accepted is already durable and a crash
 * one millisecond later loses nothing.
 */
export class JobService {
  constructor(private readonly deps: JobServiceDeps) {}

  async create(input: CreateJobInput): Promise<Job> {
    const [job] = await this.createMany([input.accountId], input.action, input);
    if (job === undefined) throw new JobNotFoundError('unknown');
    return job;
  }

  /** Compose sends one action to several accounts; each gets its own job. */
  async createBatch(input: CreateJobBatchInput): Promise<Job[]> {
    return this.createMany(input.accountIds, input.action, input);
  }

  /**
   * One post, many groups, many accounts: a job per account and group, in the
   * order given. The timeline share, when asked for, rides on the first group
   * job only, so a run over forty groups does not post forty times to the
   * account's own timeline.
   */
  async createShareToGroups(request: ShareToGroupsRequest): Promise<Job[]> {
    const accounts = await this.usableAccounts(request.accountIds);
    const actions: Array<{ accountId: string; action: AutomationActionInput }> = [];

    for (const account of accounts) {
      const done = request.skipDone
        ? await this.deps.repositories.activities.doneTargets(account.id, 'share')
        : new Set<string>();

      let first = true;
      for (const group of request.groups) {
        const key = `${request.postUrl}::${group.url ?? group.name}`;
        if (done.has(key)) continue;

        actions.push({
          accountId: account.id,
          action: {
            type: 'share_to_group',
            postUrl: request.postUrl,
            groupName: group.name,
            groupUrl: group.url,
            shareToTimeline: first && request.shareToTimeline,
            reaction: request.reaction,
            comments: [...request.comments],
          },
        });
        first = false;
      }
    }

    return this.createMixed(actions, { priority: request.priority ?? 0 });
  }

  async createJoinGroups(request: JoinGroupsRequest): Promise<Job[]> {
    const accounts = await this.usableAccounts(request.accountIds);
    const actions: Array<{ accountId: string; action: AutomationActionInput }> = [];

    for (const account of accounts) {
      const done = request.skipDone
        ? await this.deps.repositories.activities.doneTargets(account.id, 'join')
        : new Set<string>();

      for (const groupUrl of request.groupUrls) {
        if (done.has(groupUrl)) continue;
        actions.push({ accountId: account.id, action: { type: 'join_group', groupUrl } });
      }
    }

    return this.createMixed(actions, { priority: request.priority ?? 0 });
  }

  /**
   * One post, many accounts, one comment each: account n gets line n, and the
   * lines repeat when the accounts outnumber them. With skipDone, an account
   * that already commented, reacted or shared this post does not do it again,
   * so the same roster can be run twice without doubling up.
   */
  async createCommentPost(request: CommentPostRequest): Promise<Job[]> {
    const accounts = await this.usableAccounts(request.accountIds);
    const { activities } = this.deps.repositories;
    const actions: Array<{ accountId: string; action: AutomationActionInput }> = [];
    const { postUrl } = request;

    for (const [index, account] of accounts.entries()) {
      const text = request.comments[index % request.comments.length];
      if (text === undefined) break;
      const did = async (kind: ActivityKind, target: string): Promise<boolean> =>
        request.skipDone && (await activities.doneTargets(account.id, kind)).has(target);

      const commented = await did('comment', postUrl);
      if (request.then === 'timeline' || request.then === 'story') {
        // A share job comments once the share is up, so one job covers both
        // unless the share already happened and only the comment is owed.
        if (!(await did('share', `${postUrl}::${request.then}`))) {
          actions.push({
            accountId: account.id,
            action: {
              type: 'share_post',
              postUrl,
              targets: [request.then],
              reaction: null,
              comments: commented ? [] : [text],
            },
          });
        } else if (!commented) {
          actions.push({ accountId: account.id, action: { type: 'comment', postUrl, text } });
        }
        continue;
      }

      if (!commented)
        actions.push({ accountId: account.id, action: { type: 'comment', postUrl, text } });
      if (request.then === 'react' && !(await did('react', postUrl))) {
        actions.push({
          accountId: account.id,
          action: { type: 'react_to_post', postUrl, reaction: request.reaction ?? 'like' },
        });
      }
    }

    return this.createMixed(actions, {
      priority: request.priority ?? 0,
      ...(request.scheduledFor === undefined ? {} : { scheduledFor: request.scheduledFor }),
    });
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

  /** The Stop button: running jobs are aborted, everything waiting is cancelled. */
  async cancelAll(): Promise<number> {
    for (const job of this.deps.queue.runningJobs()) this.deps.queue.requestCancel(job.id);
    const count = await this.deps.repositories.jobs.cancelAllActive();

    this.deps.logger.warn(`Cancelled ${count} job(s)`, { event: 'queue.cancel_all' });
    const stats = await this.deps.repositories.jobs.stats();
    this.deps.events.publish({ type: 'queue.stats', timestamp: nowIso(), payload: stats });
    return count;
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
    action: AutomationActionInput,
    options: CreateOptions,
  ): Promise<Job[]> {
    await this.usableAccounts(accountIds);
    return this.createMixed(
      accountIds.map((accountId) => ({ accountId, action })),
      options,
    );
  }

  /** Every account is checked before anything is written: a batch goes in whole or not at all. */
  private async usableAccounts(accountIds: readonly string[]) {
    const found = await this.deps.repositories.accounts.findByIds(accountIds);
    const byId = new Map(found.map((account) => [account.id, account]));
    return accountIds.map((accountId) => {
      const account = byId.get(accountId);
      if (account === undefined) throw new AccountNotFoundError(accountId);
      if (!account.enabled) throw new AccountDisabledError(accountId);
      return account;
    });
  }

  private async createMixed(
    entries: ReadonlyArray<{ accountId: string; action: AutomationActionInput }>,
    options: CreateOptions,
  ): Promise<Job[]> {
    if (entries.length === 0) return [];
    const { repositories, events, queue } = this.deps;
    const settings = await repositories.settings.read();

    const created = await repositories.jobs.createMany(
      entries.map((entry) => {
        // Parsed rather than trusted: the caller may hand us the input shape,
        // where fields with defaults are still optional.
        const action: AutomationAction = AutomationActionSchema.parse(entry.action);
        return {
          id: createId('job'),
          accountId: entry.accountId,
          type: jobTypeOf(action),
          payload: action,
          priority: options.priority ?? 0,
          maxRetries: options.maxRetries ?? settings.defaultMaxRetries,
          status: 'pending' as const,
          runAfter: options.scheduledFor ?? null,
        };
      }),
    );

    for (const job of created) {
      events.publish({ type: 'job.created', timestamp: nowIso(), payload: job });
    }

    queue.notify();
    return created;
  }
}
