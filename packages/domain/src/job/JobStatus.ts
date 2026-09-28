import type { JobStatus } from '@fb/shared';
import { TERMINAL_JOB_STATUSES } from '@fb/shared';

/**
 * Queue lifecycle.
 *
 *   pending -> queued -> running -> completed
 *                  ^        |
 *                  |        +-> retrying -> queued
 *                  |        +-> failed
 *                  +-----------------------+
 *   any non-terminal state -> cancelled
 */
const ALLOWED: Readonly<Record<JobStatus, readonly JobStatus[]>> = {
  pending: ['queued', 'cancelled'],
  queued: ['running', 'cancelled', 'pending'],
  running: ['completed', 'failed', 'retrying', 'cancelled'],
  retrying: ['queued', 'failed', 'cancelled'],
  completed: [],
  failed: ['pending'],
  cancelled: ['pending'],
};

export const canTransitionJob = (from: JobStatus, to: JobStatus): boolean =>
  (ALLOWED[from] ?? []).includes(to);

export const isTerminalJobStatus = (status: JobStatus): boolean =>
  (TERMINAL_JOB_STATUSES as readonly JobStatus[]).includes(status);

export const isCancellable = (status: JobStatus): boolean => !isTerminalJobStatus(status);

/** Only a finished, unsuccessful job can be sent round again. */
export const isRetriable = (status: JobStatus): boolean =>
  status === 'failed' || status === 'cancelled';
