import { index, integer, real, sqliteTable, text } from 'drizzle-orm/sqlite-core';
import { JOB_STATUSES, JOB_TYPES } from '@fb/shared';
import { accounts } from './accounts.js';

export const jobs = sqliteTable(
  'jobs',
  {
    id: text('id').primaryKey(),
    accountId: text('account_id')
      .notNull()
      .references(() => accounts.id, { onDelete: 'cascade' }),
    type: text('type', { enum: JOB_TYPES }).notNull(),
    status: text('status', { enum: JOB_STATUSES }).notNull().default('pending'),
    /** JSON, validated against AutomationActionSchema when it is read back. */
    payload: text('payload').notNull(),
    priority: integer('priority').notNull().default(0),
    retryCount: integer('retry_count').notNull().default(0),
    maxRetries: integer('max_retries').notNull().default(2),
    progress: real('progress').notNull().default(0),
    runAfter: text('run_after'),
    result: text('result'),
    lastError: text('last_error'),
    /** Worker that claimed the row; cleared when the job leaves `running`. */
    lockedBy: text('locked_by'),
    createdAt: text('created_at').notNull(),
    queuedAt: text('queued_at'),
    startedAt: text('started_at'),
    finishedAt: text('finished_at'),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    // Supports the claim query: due work, best priority first, oldest first.
    index('jobs_claim_idx').on(table.status, table.priority, table.createdAt),
    index('jobs_account_status_idx').on(table.accountId, table.status),
    index('jobs_run_after_idx').on(table.status, table.runAfter),
    index('jobs_created_idx').on(table.createdAt),
  ],
);

export type JobRow = typeof jobs.$inferSelect;
export type JobInsert = typeof jobs.$inferInsert;

/** Append-only audit of status changes; cheap to write, invaluable to read. */
export const jobEvents = sqliteTable(
  'job_events',
  {
    id: text('id').primaryKey(),
    jobId: text('job_id')
      .notNull()
      .references(() => jobs.id, { onDelete: 'cascade' }),
    fromStatus: text('from_status'),
    toStatus: text('to_status').notNull(),
    message: text('message'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [index('job_events_job_idx').on(table.jobId, table.createdAt)],
);

export type JobEventRow = typeof jobEvents.$inferSelect;
export type JobEventInsert = typeof jobEvents.$inferInsert;
