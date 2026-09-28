import { z } from 'zod';
import { ACCOUNT_STATUSES } from '../constants/index.js';
import { CoercedDateTimeSchema, IdSchema, PaginationSchema } from './common.js';

export const AccountStatusSchema = z.enum(ACCOUNT_STATUSES);
export type AccountStatus = z.infer<typeof AccountStatusSchema>;

/**
 * A profile slug becomes a directory name under the configured profile root,
 * so it is restricted to characters that cannot escape that directory.
 */
export const ProfileSlugSchema = z
  .string()
  .min(3)
  .max(64)
  .regex(/^[a-z0-9][a-z0-9-]*$/, 'Use lowercase letters, digits and dashes only');

export const AccountSchema = z.object({
  id: IdSchema,
  name: z.string().min(1).max(120),
  displayName: z.string().min(1).max(120),
  profileId: IdSchema,
  status: AccountStatusSchema,
  enabled: z.boolean(),
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

export const CreateAccountSchema = z.object({
  name: z.string().min(1).max(120),
  displayName: z.string().min(1).max(120).optional(),
  /** Derived from the name when omitted. */
  profileSlug: ProfileSlugSchema.optional(),
  enabled: z.boolean().default(true),
});
export type CreateAccountInput = z.input<typeof CreateAccountSchema>;

export const UpdateAccountSchema = z
  .object({
    name: z.string().min(1).max(120),
    displayName: z.string().min(1).max(120),
    enabled: z.boolean(),
  })
  .partial()
  .refine((value) => Object.keys(value).length > 0, 'Provide at least one field to update');
export type UpdateAccountInput = z.infer<typeof UpdateAccountSchema>;

export const ListAccountsQuerySchema = PaginationSchema.extend({
  search: z.string().trim().min(1).max(120).optional(),
  status: AccountStatusSchema.optional(),
  enabled: z
    .enum(['true', 'false'])
    .transform((value) => value === 'true')
    .optional(),
});
export type ListAccountsQuery = z.infer<typeof ListAccountsQuerySchema>;

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
  skipped: z.array(z.object({ name: z.string(), reason: z.string() })),
});
export type ImportAccountsResult = z.infer<typeof ImportAccountsResultSchema>;
