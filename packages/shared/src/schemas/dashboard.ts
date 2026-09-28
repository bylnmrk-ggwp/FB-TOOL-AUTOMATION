import { z } from 'zod';
import { QueueStatsSchema } from './job.js';
import { LogEntrySchema } from './log.js';

export const DashboardStatsSchema = z.object({
  accounts: z.object({
    total: z.number().int().min(0),
    enabled: z.number().int().min(0),
    online: z.number().int().min(0),
    busy: z.number().int().min(0),
    error: z.number().int().min(0),
  }),
  queue: QueueStatsSchema,
  jobs: z.object({
    last24h: z.number().int().min(0),
    succeededLast24h: z.number().int().min(0),
    failedLast24h: z.number().int().min(0),
  }),
  health: z.object({
    status: z.enum(['ok', 'degraded']),
    workersBusy: z.number().int().min(0),
    workerCapacity: z.number().int().min(0),
  }),
  recentActivity: z.array(LogEntrySchema),
});
export type DashboardStats = z.infer<typeof DashboardStatsSchema>;
