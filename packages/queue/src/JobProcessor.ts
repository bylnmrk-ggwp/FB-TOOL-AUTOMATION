import {
  createId,
  ERROR_CODES,
  isAppError,
  JobCancelledError,
  nowIso,
  ShareRestrictedError,
  type ActivityKind,
  type BrowserSessionView,
  type Job,
  type JobError,
  type LoginStatus,
} from '@fb/shared';
import {
  classifyError,
  isShareRestricted,
  type AutomationGateway,
  type FetchedGroup,
} from '@fb/domain';
import type {
  AccountService,
  BrowserService,
  EventPublisher,
  GroupService,
  Logger,
  OperatorInputService,
  Repositories,
} from '@fb/application';
import type { RetryManager } from './RetryManager.js';

export interface JobProcessorDeps {
  repositories: Repositories;
  gateway: AutomationGateway;
  browsers: BrowserService;
  accounts: AccountService;
  groups: GroupService;
  operator: OperatorInputService;
  retries: RetryManager;
  events: EventPublisher;
  logger: Logger;
}

export interface JobOutcome {
  job: Job;
  status: 'completed' | 'failed' | 'retrying' | 'cancelled';
}

/** Hours Facebook's share block is honoured before share jobs run again. */
const SHARE_RESTRICTION_HOURS = 12;

/**
 * Runs exactly one job from `queued` to a terminal state.
 *
 * It owns the whole of one attempt: making sure a browser is there, marking
 * the account busy, handing the action to the gateway, and writing down what
 * happened — including what the result means for the account, such as a new
 * login verdict or a fresh list of groups. Deciding *which* job runs, and how
 * many at once, belongs to the worker above it.
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
    let openedHere = false;
    // Set when the account never got past Facebook's login screen or a gate:
    // there is nothing to keep open for it, and the next account should
    // have its slot.
    let gatedOut = false;

    try {
      await this.refuseIfShareRestricted(started);

      // A job needs a browser. Starting one here — rather than refusing —
      // means a queued job survives an operator having closed the window.
      const browser = await this.ensureBrowser(started);
      const session = browser.session;
      openedHere = browser.openedHere;
      await this.setAccountStatus(started.accountId, 'busy');

      const result = await this.deps.gateway.execute(started.payload, {
        jobId: started.id,
        accountId: started.accountId,
        sessionId: session.sessionId,
        signal,
        // A watch is one step that lasts the whole job; everything else is
        // many steps that each get the configured budget.
        timeoutMs: settings.defaultTimeoutMs,
        delayRangeMs: [settings.minActionDelayMs, settings.maxActionDelayMs],
        settings,
        onProgress: (progress, step) => {
          void this.reportProgress(started, progress, step);
        },
        askOperator: (request) =>
          this.deps.operator.ask({
            jobId: started.id,
            accountId: started.accountId,
            kind: request.kind,
            message: request.message,
            ...(request.expectsText === undefined ? {} : { expectsText: request.expectsText }),
            timeoutMs: settings.operatorInputTimeoutMs,
            signal,
          }),
      });

      await this.applyResult(started, result.details);

      const completed = await repositories.jobs.update(started.id, {
        status: 'completed',
        progress: 100,
        result,
        finishedAt: nowIso(),
        lastError: null,
      });

      log.info('Job completed', { event: 'job.completed', durationMs: Date.now() - startedAtMs });
      events.publish({ type: 'job.completed', timestamp: nowIso(), payload: completed });

      return { job: completed, status: 'completed' };
    } catch (error) {
      gatedOut =
        isAppError(error) &&
        (error.code === ERROR_CODES.AUTOMATION_NOT_LOGGED_IN ||
          error.code === ERROR_CODES.AUTOMATION_GATED);
      await this.applyFailure(started, error);
      return this.handleFailure(started, error, signal);
    } finally {
      // Close the browser this job opened, so a batch across many accounts
      // does not leave a Chromium per account running until the machine is
      // out of memory. A browser opened by an operator (openedHere false) is
      // left alone — a person may still be in it. A watch-live browser is
      // left open too, since the open page is the viewer — unless the
      // account never got in, in which case it is only a window on a login
      // screen and the lane moves on to the next account.
      if (
        openedHere &&
        (started.type !== 'watch_live' || gatedOut) &&
        this.deps.browsers.isRunning(started.accountId)
      ) {
        try {
          await this.deps.browsers.stop(started.accountId, 'job finished');
        } catch (error) {
          this.deps.logger.warn('Could not close the job browser', {
            event: 'browser.close_failed',
            accountId: started.accountId,
            reason: error instanceof Error ? error.message : String(error),
          });
        }
      }
      // The account goes back to idle whatever happened, so one bad job does
      // not leave an account looking busy for ever.
      await this.setAccountStatus(started.accountId, 'online');
    }
  }

  /** What a successful result means for the rest of the system. */
  private async applyResult(job: Job, details: Record<string, unknown>): Promise<void> {
    const { accounts, groups, repositories } = this.deps;

    switch (job.type) {
      case 'login':
      case 'check_login': {
        const status = details['loginStatus'];
        if (typeof status === 'string') {
          await accounts.recordLoginVerdict(job.accountId, {
            loginStatus: status as LoginStatus,
            loginReason: typeof details['loginReason'] === 'string' ? details['loginReason'] : null,
            facebookName:
              typeof details['facebookName'] === 'string' ? details['facebookName'] : null,
            profileUrl: typeof details['profileUrl'] === 'string' ? details['profileUrl'] : null,
          });
        }
        return;
      }
      case 'fetch_groups': {
        const fetched = Array.isArray(details['groups'])
          ? (details['groups'] as FetchedGroup[])
          : [];
        await groups.recordFetched(job.accountId, fetched);
        return;
      }
      case 'share_to_group': {
        if (job.payload.type !== 'share_to_group') return;
        await repositories.activities.record({
          id: createId('act'),
          accountId: job.accountId,
          kind: 'share',
          targetUrl: `${job.payload.postUrl}::${job.payload.groupUrl ?? job.payload.groupName}`,
          targetName:
            typeof details['group'] === 'string' ? details['group'] : job.payload.groupName,
          status: 'done',
          message: null,
          jobId: job.id,
        });
        return;
      }
      case 'join_group': {
        if (job.payload.type !== 'join_group') return;
        const outcome = typeof details['outcome'] === 'string' ? details['outcome'] : 'joined';
        await repositories.activities.record({
          id: createId('act'),
          accountId: job.accountId,
          kind: 'join',
          targetUrl: job.payload.groupUrl,
          targetName: null,
          status: outcome === 'pending' ? 'pending' : 'done',
          message: typeof details['message'] === 'string' ? details['message'] : null,
          jobId: job.id,
        });
        return;
      }
      case 'comment': {
        if (job.payload.type !== 'comment') return;
        await this.recordDone(job, 'comment', job.payload.postUrl, job.payload.text.slice(0, 300));
        return;
      }
      case 'react_to_post': {
        if (job.payload.type !== 'react_to_post') return;
        await this.recordDone(job, 'react', job.payload.postUrl, job.payload.reaction);
        return;
      }
      case 'share_post': {
        if (job.payload.type !== 'share_post') return;
        // The share action reports each target it landed on, plus the reaction
        // and the comment it added, so a later run skips exactly those.
        for (const target of job.payload.targets) {
          if (details[target] === 'shared')
            await this.recordDone(job, 'share', `${job.payload.postUrl}::${target}`, null);
        }
        if (typeof details['reaction'] === 'string')
          await this.recordDone(job, 'react', job.payload.postUrl, details['reaction']);
        if (typeof details['comment'] === 'string')
          await this.recordDone(
            job,
            'comment',
            job.payload.postUrl,
            details['comment'].slice(0, 300),
          );
        return;
      }
      default:
        return;
    }
  }

  /** One thing this account has now done to one target, so it is not done twice. */
  private recordDone(
    job: Job,
    kind: ActivityKind,
    targetUrl: string,
    message: string | null,
  ): Promise<unknown> {
    return this.deps.repositories.activities.record({
      id: createId('act'),
      accountId: job.accountId,
      kind,
      targetUrl,
      targetName: null,
      status: 'done',
      message,
      jobId: job.id,
    });
  }

  /** What a failure means for the account, before the job itself is judged. */
  private async applyFailure(job: Job, error: unknown): Promise<void> {
    if (error instanceof ShareRestrictedError) {
      await this.deps.accounts.recordShareRestriction(
        job.accountId,
        SHARE_RESTRICTION_HOURS,
        error.message,
      );
    }
    // Any job can find the session gone — a watch, a share, a comment. That
    // is a fact about the account, not the job, so the roster records it and
    // the next "logged in" selection leaves this account out.
    if (
      isAppError(error) &&
      error.code === ERROR_CODES.AUTOMATION_NOT_LOGGED_IN &&
      job.type !== 'login' &&
      job.type !== 'check_login'
    ) {
      await this.deps.accounts.recordLoginVerdict(job.accountId, {
        loginStatus: 'logged_out',
        loginReason: error.message,
      });
      return;
    }
    if ((job.type === 'login' || job.type === 'check_login') && isAppError(error)) {
      const gate = (error.details as { gate?: unknown } | undefined)?.gate;
      if (isLoginStatus(gate)) {
        await this.deps.accounts.recordLoginVerdict(job.accountId, {
          loginStatus: gate,
          loginReason: error.message,
        });
      } else if (error.code === ERROR_CODES.AUTOMATION_LOGIN_FAILED && !error.retryable) {
        // Facebook itself refused: wrong password, or the form never left.
        await this.deps.accounts.recordLoginVerdict(job.accountId, {
          loginStatus: 'logged_out',
          loginReason: error.message,
        });
      }
      // Anything else — a browser that would not launch, a page that timed
      // out, the server stopping — is the machine failing, not the account.
      // The last real verdict stands, so an overloaded batch cannot mark a
      // working account as logged out.
    }
  }

  /** A share job on a restricted account is failed now rather than tried and refused. */
  private async refuseIfShareRestricted(job: Job): Promise<void> {
    if (job.type !== 'share_post' && job.type !== 'share_to_group') return;
    const account = await this.deps.repositories.accounts.findById(job.accountId);
    if (account !== null && isShareRestricted(account)) {
      throw new ShareRestrictedError(job.accountId, account.shareRestrictedUntil);
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

  /**
   * The browser a job runs in. Reuses one already open — an operator's window,
   * or a browser a previous job left for reuse — and otherwise opens one,
   * reporting which, so the caller closes only what it opened. Without that a
   * batch across many accounts opens a browser per account and never closes
   * one, and the machine runs out of memory long before the queue drains.
   */
  private async ensureBrowser(
    job: Job,
  ): Promise<{ session: BrowserSessionView; openedHere: boolean }> {
    const existing = this.deps.browsers.get(job.accountId);
    if (existing !== null) return { session: existing, openedHere: false };
    // A viewer needs the video to actually play, which a lite headless
    // browser cannot do: it drops every media request.
    const needsMedia = job.type === 'watch_live';
    return {
      session: await this.deps.browsers.start(job.accountId, undefined, needsMedia),
      openedHere: true,
    };
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

const isLoginStatus = (value: unknown): value is LoginStatus =>
  typeof value === 'string' &&
  ['checkpoint', 'two_factor', 'email_confirmation', 'captcha', 'disabled', 'logged_out'].includes(
    value,
  );
