import { z } from 'zod';
import { POST_AUDIENCES, REACTION_TYPES, SHARE_TARGETS } from '../constants/index.js';

export const ReactionTypeSchema = z.enum(REACTION_TYPES);
export type ReactionType = z.infer<typeof ReactionTypeSchema>;

export const PostAudienceSchema = z.enum(POST_AUDIENCES);
export type PostAudience = z.infer<typeof PostAudienceSchema>;

export const ShareTargetSchema = z.enum(SHARE_TARGETS);
export type ShareTarget = z.infer<typeof ShareTargetSchema>;

/**
 * Media is referenced by the id the upload endpoint handed back, never by a
 * client-supplied filesystem path. The server resolves the id inside the
 * configured upload directory.
 */
export const MediaRefSchema = z.object({
  id: z.string().min(1).max(128),
  fileName: z.string().min(1).max(255),
  mimeType: z.string().min(1).max(127),
  sizeBytes: z.number().int().positive(),
});
export type MediaRef = z.infer<typeof MediaRefSchema>;

/** A Facebook URL, with the mobile hosts folded into the desktop one. */
export const FacebookUrlSchema = z
  .string()
  .trim()
  .min(1)
  .transform((value) => (value.startsWith('http') ? value : `https://www.facebook.com/${value}`))
  .transform((value) =>
    value
      .replace('://m.facebook.com', '://www.facebook.com')
      .replace('://mobile.facebook.com', '://www.facebook.com'),
  )
  .pipe(z.string().url().max(1_000));

/**
 * Comments are a pool: one line is chosen at random per run, so a batch across
 * many accounts does not leave the same sentence under a post forty times.
 */
const CommentPoolSchema = z.array(z.string().trim().min(1).max(8_000)).max(50).default([]);

export const CreatePostPayloadSchema = z.object({
  type: z.literal('create_post'),
  text: z.string().min(1).max(63_206),
  media: z.array(MediaRefSchema).max(10).default([]),
  audience: PostAudienceSchema.default('friends'),
});

export const UploadMediaPayloadSchema = z.object({
  type: z.literal('upload_media'),
  targetUrl: FacebookUrlSchema,
  media: z.array(MediaRefSchema).min(1).max(10),
  caption: z.string().max(63_206).optional(),
});

export const CommentPayloadSchema = z.object({
  type: z.literal('comment'),
  postUrl: FacebookUrlSchema,
  text: z.string().min(1).max(8_000),
});

export const ReactToPostPayloadSchema = z.object({
  type: z.literal('react_to_post'),
  postUrl: FacebookUrlSchema,
  reaction: ReactionTypeSchema.default('like'),
});

export const SendMessagePayloadSchema = z.object({
  type: z.literal('send_message'),
  /** Messenger thread id or profile id of the recipient. */
  threadId: z.string().min(1).max(128),
  text: z.string().min(1).max(20_000),
  media: z.array(MediaRefSchema).max(10).default([]),
});

/** Share somebody else's post onto this account's own timeline, story or feed. */
export const SharePostPayloadSchema = z.object({
  type: z.literal('share_post'),
  postUrl: FacebookUrlSchema,
  targets: z.array(ShareTargetSchema).min(1).default(['timeline']),
  reaction: ReactionTypeSchema.nullable().default(null),
  comments: CommentPoolSchema,
});

export const ShareToGroupPayloadSchema = z.object({
  type: z.literal('share_to_group'),
  postUrl: FacebookUrlSchema,
  groupName: z.string().trim().min(1).max(200),
  groupUrl: FacebookUrlSchema.nullable().default(null),
  /** Also share to the timeline and story first; off for every group after the first. */
  shareToTimeline: z.boolean().default(false),
  reaction: ReactionTypeSchema.nullable().default(null),
  comments: CommentPoolSchema,
});

export const JoinGroupPayloadSchema = z.object({
  type: z.literal('join_group'),
  groupUrl: FacebookUrlSchema,
});

export const FetchGroupsPayloadSchema = z.object({
  type: z.literal('fetch_groups'),
});

/** Sign in with the stored username and password; a person finishes any gate. */
export const LoginPayloadSchema = z.object({
  type: z.literal('login'),
  /** When false, a checkpoint or code prompt fails the job instead of waiting. */
  waitForOperator: z.boolean().default(true),
});

export const CheckLoginPayloadSchema = z.object({
  type: z.literal('check_login'),
});

export const AcceptFriendRequestsPayloadSchema = z.object({
  type: z.literal('accept_friend_requests'),
  max: z.number().int().min(1).max(500).default(100),
});

export const AddFriendsPayloadSchema = z.object({
  type: z.literal('add_friends'),
  /** Stop once this many requests have been sent in this run. */
  target: z.number().int().min(1).max(500).default(50),
});

export const AutoSetupProfilePayloadSchema = z.object({
  type: z.literal('auto_setup_profile'),
  targetFriends: z.number().int().min(0).max(5_000).default(50),
  /** Below this, suggestions are skipped: the accounts will befriend each other. */
  connectFriends: z.boolean().default(true),
  bio: z.string().trim().max(500).nullable().default(null),
  profilePicture: MediaRefSchema.nullable().default(null),
});

/** Keep a live video playing in this account's browser for a while. */
export const WatchLivePayloadSchema = z.object({
  type: z.literal('watch_live'),
  url: FacebookUrlSchema,
  /** Null watches until the broadcast ends or the job is cancelled. */
  minutes: z
    .number()
    .min(1)
    .max(24 * 60)
    .nullable()
    .default(null),
});

/** The complete set of actions the automation engine can execute. */
export const AutomationActionSchema = z.discriminatedUnion('type', [
  CreatePostPayloadSchema,
  UploadMediaPayloadSchema,
  CommentPayloadSchema,
  ReactToPostPayloadSchema,
  SendMessagePayloadSchema,
  SharePostPayloadSchema,
  ShareToGroupPayloadSchema,
  JoinGroupPayloadSchema,
  FetchGroupsPayloadSchema,
  LoginPayloadSchema,
  CheckLoginPayloadSchema,
  AcceptFriendRequestsPayloadSchema,
  AddFriendsPayloadSchema,
  AutoSetupProfilePayloadSchema,
  WatchLivePayloadSchema,
]);
export type AutomationAction = z.infer<typeof AutomationActionSchema>;
export type AutomationActionInput = z.input<typeof AutomationActionSchema>;

export const AutomationResultSchema = z.object({
  /** Facebook permalink or thread url produced by the action, when there is one. */
  resourceUrl: z.string().url().nullable(),
  durationMs: z.number().int().nonnegative(),
  screenshotPath: z.string().nullable(),
  details: z.record(z.unknown()).default({}),
});
export type AutomationResult = z.infer<typeof AutomationResultSchema>;
