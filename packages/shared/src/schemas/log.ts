import { z } from 'zod';
import { LOG_LEVELS } from '../constants/index.js';
import { CoercedDateTimeSchema, IdSchema, IsoDateTimeSchema, PaginationSchema } from './common.js';

export const LogLevelSchema = z.enum(LOG_LEVELS);
export type LogLevel = z.infer<typeof LogLevelSchema>;

export const LogEntrySchema = z.object({
  id: IdSchema,
  level: LogLevelSchema,
  message: z.string(),
  /** Dotted event name, e.g. `job.started`. Free-form text stays in `message`. */
  event: z.string().nullable(),
  accountId: IdSchema.nullable(),
  jobId: IdSchema.nullable(),
  sessionId: IdSchema.nullable(),
  requestId: IdSchema.nullable(),
  context: z.record(z.unknown()).nullable(),
  createdAt: CoercedDateTimeSchema,
});
export type LogEntry = z.infer<typeof LogEntrySchema>;

export const ListLogsQuerySchema = PaginationSchema.extend({
  level: z
    .union([LogLevelSchema, z.array(LogLevelSchema)])
    .transform((value) => (Array.isArray(value) ? value : [value]))
    .optional(),
  accountId: IdSchema.optional(),
  jobId: IdSchema.optional(),
  event: z.string().max(120).optional(),
  search: z.string().trim().min(1).max(200).optional(),
  from: IsoDateTimeSchema.optional(),
  to: IsoDateTimeSchema.optional(),
});
export type ListLogsQuery = z.infer<typeof ListLogsQuerySchema>;
