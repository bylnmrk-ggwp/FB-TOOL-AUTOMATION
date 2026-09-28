import { z } from 'zod';
import { LOGIN_STATUSES } from '../constants/index.js';
import { QueueStatsSchema } from './job.js';
import { LogEntrySchema } from './log.js';

/** One bucket of the activity chart: what finished in that hour. */
export const HourlyJobsSchema = z.object({
  /** Start of the hour, ISO-8601 UTC. */
  hour: z.string(),
  completed: z.number().int().min(0),
  failed: z.number().int().min(0),
  cancelled: z.number().int().min(0),
});
export type HourlyJobs = z.infer<typeof HourlyJobsSchema>;

export const DashboardStatsSchema = z.object({
  accounts: z.object({
    total: z.number().int().min(0),
    enabled: z.number().int().min(0),
    online: z.number().int().min(0),
    busy: z.number().int().min(0),
    error: z.number().int().min(0),
    /** How many accounts sit in each login state, for the roster donut. */
    byLoginStatus: z.record(z.enum(LOGIN_STATUSES), z.number().int().min(0)),
  }),
  queue: QueueStatsSchema,
  jobs: z.object({
    last24h: z.number().int().min(0),
    succeededLast24h: z.number().int().min(0),
    failedLast24h: z.number().int().min(0),
    /** The last 24 hours, one entry per hour, oldest first, gaps filled with zeros. */
    hourly: z.array(HourlyJobsSchema),
    /** Finished jobs in the last 24 hours by type, most first. */
    byType: z.array(z.object({ type: z.string(), count: z.number().int().min(0) })),
  }),
  health: z.object({
    status: z.enum(['ok', 'degraded']),
    workersBusy: z.number().int().min(0),
    workerCapacity: z.number().int().min(0),
  }),
  recentActivity: z.array(LogEntrySchema),
});
export type DashboardStats = z.infer<typeof DashboardStatsSchema>;
