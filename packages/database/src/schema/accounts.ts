import { index, integer, sqliteTable, text, uniqueIndex } from 'drizzle-orm/sqlite-core';
import { ACCOUNT_STATUSES, LOGIN_STATUSES } from '@fb/shared';

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

    // Roster fields. Column names follow the sheet's headers so an import
    // maps header to column by name. Passwords are stored as the operator
    // supplied them: the login action types them into Facebook, and there is
    // no way to do that from a hash. Treat the database file as a credential.
    sheetNo: integer('sheet_no'),
    username: text('username'),
    password: text('password'),
    gmail: text('gmail'),
    gmailPassword: text('gmail_password'),
    phone: text('phone'),
    facebookName: text('facebook_name'),
    profileUrl: text('profile_url'),
    // The proxy string with its credentials, as pasted; parsed at launch.
    proxyUrl: text('proxy_url'),
    // Base32 authenticator secret, for answering two-factor at login.
    totpSecret: text('totp_secret'),

    loginStatus: text('login_status', { enum: LOGIN_STATUSES }).notNull().default('unknown'),
    loginReason: text('login_reason'),
    lastLoginCheckAt: text('last_login_check_at'),
    shareRestrictedUntil: text('share_restricted_until'),

    createdAt: text('created_at').notNull(),
    updatedAt: text('updated_at').notNull(),
  },
  (table) => [
    uniqueIndex('accounts_name_unique').on(table.name),
    index('accounts_status_idx').on(table.status),
    index('accounts_enabled_idx').on(table.enabled),
    index('accounts_username_idx').on(table.username),
    index('accounts_login_status_idx').on(table.loginStatus),
  ],
);

export type AccountRow = typeof accounts.$inferSelect;
export type AccountInsert = typeof accounts.$inferInsert;
