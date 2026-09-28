import { z } from 'zod';
import { ACCOUNT_STATUSES, LOGIN_STATUSES } from '../constants/index.js';
import { CoercedDateTimeSchema, IdSchema, PaginationSchema } from './common.js';

export const AccountStatusSchema = z.enum(ACCOUNT_STATUSES);
export type AccountStatus = z.infer<typeof AccountStatusSchema>;

export const LoginStatusSchema = z.enum(LOGIN_STATUSES);
export type LoginStatus = z.infer<typeof LoginStatusSchema>;

/**
 * A profile slug becomes a directory name under the configured profile root,
 * so it is restricted to characters that cannot escape that directory.
 */
export const ProfileSlugSchema = z
  .string()
  .min(3)
  .max(64)
  .regex(/^[a-z0-9][a-z0-9-]*$/, 'Use lowercase letters, digits and dashes only');

/**
 * What the roster knows about an account. Secrets never leave the server:
 * the API reports whether a password is stored, and accepts a new one, but
 * does not read it back.
 */
export const AccountSchema = z.object({
  id: IdSchema,
  name: z.string().min(1).max(120),
  displayName: z.string().min(1).max(120),
  profileId: IdSchema,
  status: AccountStatusSchema,
  enabled: z.boolean(),

  /** Row number on the roster sheet, when the account was imported. */
  sheetNo: z.number().int().nullable(),
  /** The Facebook sign-in identifier: email, phone or username. */
  username: z.string().max(200).nullable(),
  hasPassword: z.boolean(),
  gmail: z.string().max(200).nullable(),
  hasGmailPassword: z.boolean(),
  phone: z.string().max(60).nullable(),
  /** The name Facebook shows, as last read from the profile. */
  facebookName: z.string().max(200).nullable(),
  profileUrl: z.string().max(500).nullable(),

  loginStatus: LoginStatusSchema,
  loginReason: z.string().nullable(),
  lastLoginCheckAt: CoercedDateTimeSchema.nullable(),
  /** Facebook stopped this account sharing; other actions still work. */
  shareRestrictedUntil: CoercedDateTimeSchema.nullable(),

  lastError: z.string().nullable(),
  lastActiveAt: CoercedDateTimeSchema.nullable(),
  createdAt: CoercedDateTimeSchema,
  updatedAt: CoercedDateTimeSchema,
});
export type Account = z.infer<typeof AccountSchema>;

export const BrowserProfileSchema = z.object({
  id: IdSchema,
  accountId: IdSchema,
  slug: ProfileSlugSchema,
  /** Path relative to the configured profile root. Never an absolute path. */
  directory: z.string().min(1),
  channel: z.string().min(1),
  lockedBy: z.string().nullable(),
  lockedAt: CoercedDateTimeSchema.nullable(),
  lastUsedAt: CoercedDateTimeSchema.nullable(),
  createdAt: CoercedDateTimeSchema,
  updatedAt: CoercedDateTimeSchema,
});
export type BrowserProfile = z.infer<typeof BrowserProfileSchema>;

/** The writable credential and roster fields, shared by create and update. */
export const AccountCredentialsSchema = z.object({
  username: z.string().trim().max(200).nullable().optional(),
  /** Empty string leaves the stored password alone; null clears it. */
  password: z.string().max(200).nullable().optional(),
  gmail: z.string().trim().max(200).nullable().optional(),
  gmailPassword: z.string().max(200).nullable().optional(),
  phone: z.string().trim().max(60).nullable().optional(),
  facebookName: z.string().trim().max(200).nullable().optional(),
  sheetNo: z.number().int().nullable().optional(),
});
export type AccountCredentialsInput = z.infer<typeof AccountCredentialsSchema>;

export const CreateAccountSchema = AccountCredentialsSchema.extend({
  name: z.string().min(1).max(120),
  displayName: z.string().min(1).max(120).optional(),
  /** Derived from the name when omitted. */
  profileSlug: ProfileSlugSchema.optional(),
  enabled: z.boolean().default(true),
});
export type CreateAccountInput = z.input<typeof CreateAccountSchema>;

export const UpdateAccountSchema = AccountCredentialsSchema.extend({
  name: z.string().min(1).max(120).optional(),
  displayName: z.string().min(1).max(120).optional(),
  enabled: z.boolean().optional(),
}).refine((value) => Object.keys(value).length > 0, 'Provide at least one field to update');
export type UpdateAccountInput = z.infer<typeof UpdateAccountSchema>;

export const ListAccountsQuerySchema = PaginationSchema.extend({
  search: z.string().trim().min(1).max(120).optional(),
  status: AccountStatusSchema.optional(),
  loginStatus: LoginStatusSchema.optional(),
  enabled: z
    .enum(['true', 'false'])
    .transform((value) => value === 'true')
    .optional(),
});
export type ListAccountsQuery = z.infer<typeof ListAccountsQuerySchema>;

export const AccountIdsSchema = z.object({
  accountIds: z.array(IdSchema).min(1).max(5000),
});
export type AccountIdsInput = z.infer<typeof AccountIdsSchema>;

export const StartBrowserSchema = z.object({
  headless: z.boolean().optional(),
});
export type StartBrowserInput = z.infer<typeof StartBrowserSchema>;

export const BrowserSessionSchema = z.object({
  accountId: IdSchema,
  sessionId: IdSchema,
  status: AccountStatusSchema,
  headless: z.boolean(),
  startedAt: CoercedDateTimeSchema,
  currentUrl: z.string().nullable(),
});
export type BrowserSessionView = z.infer<typeof BrowserSessionSchema>;

export const ImportAccountsSchema = z.object({
  accounts: z.array(CreateAccountSchema).min(1).max(500),
  /** Existing accounts with the same name are updated instead of rejected. */
  upsert: z.boolean().default(false),
});
export type ImportAccountsInput = z.input<typeof ImportAccountsSchema>;

export const ImportAccountsResultSchema = z.object({
  created: z.number().int().min(0),
  updated: z.number().int().min(0),
  /** Roster accounts dropped because their row no longer counts (no username or password). */
  removed: z.number().int().min(0),
  skipped: z.array(z.object({ name: z.string(), reason: z.string() })),
});
export type ImportAccountsResult = z.infer<typeof ImportAccountsResultSchema>;

/**
 * One row read from a roster workbook. Columns are matched by header label,
 * never by position, so the sheet can be reordered freely.
 */
export const RosterRowSchema = z.object({
  /** Column A on the sheet: the row's number, and the key an import matches on. */
  sheetNo: z.number().int().nullable(),
  facebookName: z.string().nullable(),
  /** Both required: a row that cannot sign in does not count as an account. */
  username: z.string().min(1),
  password: z.string().min(1),
  gmail: z.string().nullable(),
  gmailPassword: z.string().nullable(),
  phone: z.string().nullable(),
});
export type RosterRow = z.infer<typeof RosterRowSchema>;

/** Playwright's storage state, the portable form of a signed-in session. */
export const StorageStateSchema = z.object({
  cookies: z.array(
    z.object({
      name: z.string(),
      value: z.string(),
      domain: z.string(),
      path: z.string(),
      expires: z.number(),
      httpOnly: z.boolean(),
      secure: z.boolean(),
      sameSite: z.enum(['Strict', 'Lax', 'None']),
    }),
  ),
  origins: z.array(
    z.object({
      origin: z.string(),
      localStorage: z.array(z.object({ name: z.string(), value: z.string() })),
    }),
  ),
});
export type StorageState = z.infer<typeof StorageStateSchema>;

export const SessionExportSchema = z.object({
  accountId: IdSchema,
  accountName: z.string(),
  exportedAt: CoercedDateTimeSchema,
  state: StorageStateSchema,
});
export type SessionExport = z.infer<typeof SessionExportSchema>;
