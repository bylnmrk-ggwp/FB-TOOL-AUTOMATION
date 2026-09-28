import type { Job } from '@fb/shared';

/** What the HTTP layer is allowed to ask of the running queue. */
export interface QueuePort {
  /** Nudges the worker loop after a new job is written. */
  notify(): void;
  /** Aborts a running job. Returns false when the job is not running here. */
  requestCancel(jobId: string): boolean;
  runningJobs(): readonly Job[];
  capacity(): { busy: number; limit: number };
}
