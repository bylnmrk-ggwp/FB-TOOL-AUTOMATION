import type { AutomationAction, Job, JobError, JobStatus, JobType } from '@fb/shared';
import { backoffDelayMs, DEFAULTS } from '@fb/shared';

export type { Job };

export interface NewJob {
  id: string;
  accountId: string;
  type: JobType;
  payload: AutomationAction;
  priority: number;
  maxRetries: number;
  status: JobStatus;
  /** Null means "run as soon as a worker is free". */
  runAfter: string | null;
}

export interface JobPatch {
  status?: JobStatus;
  progress?: number;
  retryCount?: number;
  runAfter?: string | null;
  result?: Job['result'];
  lastError?: JobError | null;
  queuedAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
}

export const jobTypeOf = (action: AutomationAction): JobType => action.type;

/** A job has attempts left only while the error that stopped it was retryable. */
export const hasRetriesLeft = (job: Job): boolean =>
  job.retryCount < job.maxRetries && (job.lastError?.retryable ?? true);

export const nextAttemptAt = (
  job: Job,
  now: Date,
  baseDelayMs: number = DEFAULTS.retryBackoffMs,
): Date => {
  const delay = backoffDelayMs(job.retryCount + 1, baseDelayMs, DEFAULTS.retryBackoffMaxMs);
  return new Date(now.getTime() + delay);
};

/** True when a pending or retrying job has waited long enough to be queued. */
export const isDue = (job: Job, now: Date): boolean =>
  job.runAfter === null || new Date(job.runAfter).getTime() <= now.getTime();

/**
 * Orders the queue: higher priority first, then oldest first. Returns a
 * comparator result, so it plugs straight into Array#sort.
 */
export const compareQueueOrder = (a: Job, b: Job): number => {
  if (a.priority !== b.priority) return b.priority - a.priority;
  return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
};
