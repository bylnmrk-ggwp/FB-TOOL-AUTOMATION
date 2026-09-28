import { index, sqliteTable, text, uniqueIndex } from 'drizzle-orm/sqlite-core';
import { ACTIVITY_KINDS } from '@fb/shared';
import { accounts } from './accounts.js';

/** Groups an account belongs to, as last scraped from Facebook. */
export const groups = sqliteTable(
  'groups',
  {
    id: text('id').primaryKey(),
    accountId: text('account_id')
      .notNull()
      .references(() => accounts.id, { onDelete: 'cascade' }),
    name: text('name').notNull(),
    url: text('url').notNull(),
    fetchedAt: text('fetched_at').notNull(),
  },
  (table) => [
    uniqueIndex('groups_account_url_unique').on(table.accountId, table.url),
    index('groups_url_idx').on(table.url),
  ],
);

export type GroupRow = typeof groups.$inferSelect;

/**
 * What each account has done to a target: one share per group, one join per
 * group. A bulk run reads this to skip what is already done.
 */
export const accountActivity = sqliteTable(
  'account_activity',
  {
    id: text('id').primaryKey(),
    accountId: text('account_id')
      .notNull()
      .references(() => accounts.id, { onDelete: 'cascade' }),
    kind: text('kind', { enum: ACTIVITY_KINDS }).notNull(),
    targetUrl: text('target_url').notNull(),
    targetName: text('target_name'),
    status: text('status', { enum: ['done', 'pending', 'failed'] }).notNull(),
    message: text('message'),
    jobId: text('job_id'),
    createdAt: text('created_at').notNull(),
  },
  (table) => [
    uniqueIndex('account_activity_unique').on(table.accountId, table.kind, table.targetUrl),
    index('account_activity_account_idx').on(table.accountId, table.createdAt),
  ],
);

export type ActivityRow = typeof accountActivity.$inferSelect;
