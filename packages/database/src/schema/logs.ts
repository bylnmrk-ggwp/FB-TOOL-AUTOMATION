import { index, sqliteTable, text } from 'drizzle-orm/sqlite-core';
import { LOG_LEVELS } from '@fb/shared';

export const automationLogs = sqliteTable(
  'automation_logs',
  {
    id: text('id').primaryKey(),
    level: text('level', { enum: LOG_LEVELS }).notNull(),
    message: text('message').notNull(),
    event: text('event'),
    accountId: text('account_id'),
    jobId: text('job_id'),
    sessionId: text('session_id'),
    requestId: text('request_id'),
    /** JSON, already passed through redact() before it reaches this column. */
    context: text('context'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    index('automation_logs_created_idx').on(table.createdAt),
    index('automation_logs_level_idx').on(table.level, table.createdAt),
    index('automation_logs_account_idx').on(table.accountId, table.createdAt),
    index('automation_logs_job_idx').on(table.jobId, table.createdAt),
  ],
);

export type AutomationLogRow = typeof automationLogs.$inferSelect;
export type AutomationLogInsert = typeof automationLogs.$inferInsert;
