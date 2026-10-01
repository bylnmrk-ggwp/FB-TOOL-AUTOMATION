import type { Job, JobStatus, JobType, QueueStats } from '@fb/shared';
import type { Page, PageRequest } from '../shared/index.js';
import type { JobPatch, NewJob } from './Job.js';

export interface JobFilter extends PageRequest {
  status?: readonly JobStatus[];
  accountId?: string;
  type?: JobType;
}

export interface ClaimRequest {
  /** Accounts that already have a running job and must be skipped. */
  busyAccountIds: readonly string[];
  now: Date;
  limit: number;
  /** Only these job types; the live lane claims watch_live alone. */
  types?: readonly JobType[];
  /** Never these job types; the ordinary lane leaves watch_live out. */
  excludeTypes?: readonly JobType[];
}

export interface JobRepository {
  create(job: NewJob): Promise<Job>;
  createMany(jobs: readonly NewJob[]): Promise<Job[]>;
  findById(id: string): Promise<Job | null>;
  list(filter: JobFilter): Promise<Page<Job>>;
  update(id: string, patch: JobPatch): Promise<Job>;

  /**
   * Atomically moves due jobs from `pending`/`retrying` to `queued` and returns
   * them. Doing the selection and the write in one transaction is what stops
   * two workers from picking up the same job.
   */
  claimDueJobs(request: ClaimRequest): Promise<Job[]>;

  /** Jobs left `running` by a process that died. */
  findStaleRunning(olderThan: Date): Promise<Job[]>;
  findByStatus(status: readonly JobStatus[]): Promise<Job[]>;
  /** Every job that has not finished, marked cancelled in one statement. */
  cancelAllActive(): Promise<number>;
  countRunningByAccount(): Promise<Record<string, number>>;
  stats(): Promise<QueueStats>;
  statsSince(since: Date): Promise<{ total: number; succeeded: number; failed: number }>;
  /** Finished jobs per hour since `since`, only the hours that had any. */
  finishedByHour(since: Date): Promise<Array<{ hour: string; status: JobStatus; count: number }>>;
  /** Finished jobs per type since `since`. */
  finishedByType(since: Date): Promise<Array<{ type: JobType; count: number }>>;
  deleteByAccount(accountId: string): Promise<number>;
}
