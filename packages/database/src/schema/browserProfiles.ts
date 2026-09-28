import { index, sqliteTable, text, uniqueIndex } from 'drizzle-orm/sqlite-core';
import { accounts } from './accounts.js';

export const browserProfiles = sqliteTable(
  'browser_profiles',
  {
    id: text('id').primaryKey(),
    accountId: text('account_id')
      .notNull()
      .references(() => accounts.id, { onDelete: 'cascade' }),
    slug: text('slug').notNull(),
    /** Relative to the configured profile root: an absolute path is never stored. */
    directory: text('directory').notNull(),
    channel: text('channel').notNull().default('chromium'),
    lockedBy: text('locked_by'),
    lockedAt: text('locked_at'),
    lastUsedAt: text('last_used_at'),
    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('browser_profiles_account_unique').on(table.accountId),
    uniqueIndex('browser_profiles_slug_unique').on(table.slug),
    index('browser_profiles_locked_idx').on(table.lockedBy),
  ],
);

export type BrowserProfileRow = typeof browserProfiles.$inferSelect;
export type BrowserProfileInsert = typeof browserProfiles.$inferInsert;
