import { sqliteTable, text } from 'drizzle-orm/sqlite-core';

/**
 * Key/value rather than one wide row: adding a setting is then a code change
 * and not a migration, and an unknown key can be ignored safely.
 */
export const settings = sqliteTable('settings', {
  key: text('key').primaryKey(),
  value: text('value').notNull(),
  updatedAt: text('updated_at').notNull(),
});

export type SettingRow = typeof settings.$inferSelect;
export type SettingInsert = typeof settings.$inferInsert;
