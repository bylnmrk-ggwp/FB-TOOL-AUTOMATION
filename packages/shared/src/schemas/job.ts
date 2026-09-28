import { z } from 'zod';
import { JOB_STATUSES, JOB_TYPES, PRIORITY_RANGE } from '../constants/index.js';
import { CoercedDateTimeSchema, IdSchema, IsoDateTimeSchema, PaginationSchema } from './common.js';
import { AutomationActionSchema, AutomationResultSchema } from './automation.js';

export const JobStatusSchema = z.enum(JOB_STATUSES);
export type JobStatus = z.infer<typeof JobStatusSchema>;

export const JobTypeSchema = z.enum(JOB_TYPES);
export type JobType = z.infer<typeof JobTypeSchema>;

export const JobErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  retryable: z.boolean(),
  occurredAt: CoercedDateTimeSchema,
});
export type JobError = z.infer<typeof JobErrorSchema>;

export const JobSchema = z.object({
  id: IdSchema,
  accountId: IdSchema,
  type: JobTypeSchema,
  status: JobStatusSchema,
  payload: AutomationActionSchema,
  priority: z.number().int().min(PRIORITY_RANGE.min).max(PRIORITY_RANGE.max),
  retryCount: z.number().int().min(0),
  maxRetries: z.number().int().min(0),
  progress: z.number().min(0).max(100),
  /** Earliest moment a worker may pick the job up. Drives scheduling and backoff. */
  runAfter: CoercedDateTimeSchema.nullable(),
  result: AutomationResultSchema.nullable(),
  lastError: JobErrorSchema.nullable(),
  createdAt: CoercedDateTimeSchema,
  queuedAt: CoercedDateTimeSchema.nullable(),
  startedAt: CoercedDateTimeSchema.nullable(),
  finishedAt: CoercedDateTimeSchema.nullable(),
  updatedAt: CoercedDateTimeSchema,
});
export type Job = z.infer<typeof JobSchema>;

export const CreateJobSchema = z.object({
  accountId: IdSchema,
  action: AutomationActionSchema,
  priority: z.number().int().min(PRIORITY_RANGE.min).max(PRIORITY_RANGE.max).default(0),
  maxRetries: z.number().int().min(0).max(10).optional(),
  /** Hold the job in `pending` until this moment. */
  scheduledFor: IsoDateTimeSchema.optional(),
});
export type CreateJobInput = z.input<typeof CreateJobSchema>;

/** Compose can fan one action out across several accounts in a single request. */
export const CreateJobBatchSchema = z.object({
  accountIds: z.array(IdSchema).min(1).max(200),
  action: AutomationActionSchema,
  priority: z.number().int().min(PRIORITY_RANGE.min).max(PRIORITY_RANGE.max).default(0),
  maxRetries: z.number().int().min(0).max(10).optional(),
  scheduledFor: IsoDateTimeSchema.optional(),
});
export type CreateJobBatchInput = z.input<typeof CreateJobBatchSchema>;

export const ListJobsQuerySchema = PaginationSchema.extend({
  status: z
    .union([JobStatusSchema, z.array(JobStatusSchema)])
    .transform((value) => (Array.isArray(value) ? value : [value]))
    .optional(),
  accountId: IdSchema.optional(),
  type: JobTypeSchema.optional(),
});
export type ListJobsQuery = z.infer<typeof ListJobsQuerySchema>;

export const QueueStatsSchema = z.object({
  pending: z.number().int().min(0),
  queued: z.number().int().min(0),
  running: z.number().int().min(0),
  retrying: z.number().int().min(0),
  completed: z.number().int().min(0),
  failed: z.number().int().min(0),
  cancelled: z.number().int().min(0),
});
export type QueueStats = z.infer<typeof QueueStatsSchema>;
