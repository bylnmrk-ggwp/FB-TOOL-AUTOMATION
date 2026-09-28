import { index, sqliteTable, text, integer, uniqueIndex } from 'drizzle-orm/sqlite-core';
import { ACCOUNT_STATUSES } from '@fb/shared';

export const accounts = sqliteTable(
  'accounts',
  {
    id: text('id').primaryKey(),
    name: text('name').notNull(),
    displayName: text('display_name').notNull(),
    profileId: text('profile_id').notNull(),
    status: text('status', { enum: ACCOUNT_STATUSES }).notNull().default('offline'),
    // SQLite has no boolean; 0/1 with a mode hint keeps the TS side honest.
    enabled: integer('enabled', { mode: 'boolean' }).notNull().default(true),
    lastError: text('last_error'),
    lastActiveAt: text('last_active_at'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('accounts_name_unique').on(table.name),
    index('accounts_status_idx').on(table.status),
    index('accounts_enabled_idx').on(table.enabled),
  ],
);

export type AccountRow = typeof accounts.$inferSelect;
export type AccountInsert = typeof accounts.$inferInsert;
