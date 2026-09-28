import { backoffDelayMs, DEFAULTS, type Job, type JobError } from '@fb/shared';

export interface RetryDecision {
  /** True when the job should go round again. */
  retry: boolean;
  /** When the next attempt becomes due. Null when there will not be one. */
  nextAttemptAt: Date | null;
  reason: string;
}

export interface RetryPolicyOptions {
  baseDelayMs?: number;
  maxDelayMs?: number;
}

/**
 * Decides whether a failed job deserves another attempt, and when.
 *
 * Two independent conditions have to hold: the error has to be the kind that
 * could succeed later, and the job has to have attempts left. Retrying a
 * refusal — a locked-out account, a blocked action — only repeats the refusal.
 */
export class RetryManager {
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;

  constructor(options: RetryPolicyOptions = {}) {
    this.baseDelayMs = options.baseDelayMs ?? DEFAULTS.retryBackoffMs;
    this.maxDelayMs = options.maxDelayMs ?? DEFAULTS.retryBackoffMaxMs;
  }

  decide(job: Job, error: JobError, now: Date = new Date()): RetryDecision {
    if (!error.retryable) {
      return { retry: false, nextAttemptAt: null, reason: 'The error cannot be retried' };
    }

    const attemptsUsed = job.retryCount;
    if (attemptsUsed >= job.maxRetries) {
      return {
        retry: false,
        nextAttemptAt: null,
        reason: `No attempts left (${attemptsUsed}/${job.maxRetries})`,
      };
    }

    // Jitter is what keeps a batch of jobs that failed together from coming
    // back together and failing together again.
    const delay = backoffDelayMs(attemptsUsed + 1, this.baseDelayMs, this.maxDelayMs);
    return {
      retry: true,
      nextAttemptAt: new Date(now.getTime() + delay),
      reason: `Attempt ${attemptsUsed + 2} of ${job.maxRetries + 1} in ${Math.round(delay / 1000)}s`,
    };
  }
}
