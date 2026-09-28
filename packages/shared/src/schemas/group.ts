import { z } from 'zod';
import { ACTIVITY_KINDS } from '../constants/index.js';
import { CoercedDateTimeSchema, IdSchema, PaginationSchema } from './common.js';

/** A group one account belongs to, as last read from Facebook. */
export const GroupSchema = z.object({
  id: IdSchema,
  accountId: IdSchema,
  name: z.string().min(1).max(300),
  url: z.string().url().max(1_000),
  fetchedAt: CoercedDateTimeSchema,
});
export type Group = z.infer<typeof GroupSchema>;

/** The same group seen through several accounts, for the Compose picker. */
export const GroupSummarySchema = z.object({
  url: z.string().url(),
  name: z.string(),
  accountIds: z.array(IdSchema),
});
export type GroupSummary = z.infer<typeof GroupSummarySchema>;

export const ListGroupsQuerySchema = PaginationSchema.extend({
  accountId: IdSchema.optional(),
  search: z.string().trim().min(1).max(200).optional(),
});
export type ListGroupsQuery = z.infer<typeof ListGroupsQuerySchema>;

export const ActivityKindSchema = z.enum(ACTIVITY_KINDS);
export type ActivityKind = z.infer<typeof ActivityKindSchema>;

/**
 * What an account has already done to a target, so a bulk run can skip the
 * groups it shared to yesterday instead of sharing there twice.
 */
export const ActivitySchema = z.object({
  id: IdSchema,
  accountId: IdSchema,
  kind: ActivityKindSchema,
  targetUrl: z.string().max(1_000),
  targetName: z.string().max(300).nullable(),
  status: z.enum(['done', 'pending', 'failed']),
  message: z.string().nullable(),
  jobId: IdSchema.nullable(),
  createdAt: CoercedDateTimeSchema,
});
export type Activity = z.infer<typeof ActivitySchema>;
