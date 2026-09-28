import { z } from 'zod';
import { POST_AUDIENCES, REACTION_TYPES } from '../constants/index.js';

export const ReactionTypeSchema = z.enum(REACTION_TYPES);
export type ReactionType = z.infer<typeof ReactionTypeSchema>;

export const PostAudienceSchema = z.enum(POST_AUDIENCES);
export type PostAudience = z.infer<typeof PostAudienceSchema>;

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

export const CreatePostPayloadSchema = z.object({
  type: z.literal('create_post'),
  text: z.string().min(1).max(63_206),
  media: z.array(MediaRefSchema).max(10).default([]),
  audience: PostAudienceSchema.default('friends'),
});

export const UploadMediaPayloadSchema = z.object({
  type: z.literal('upload_media'),
  targetUrl: z.string().url(),
  media: z.array(MediaRefSchema).min(1).max(10),
  caption: z.string().max(63_206).optional(),
});

export const CommentPayloadSchema = z.object({
  type: z.literal('comment'),
  postUrl: z.string().url(),
  text: z.string().min(1).max(8_000),
});

export const ReactToPostPayloadSchema = z.object({
  type: z.literal('react_to_post'),
  postUrl: z.string().url(),
  reaction: ReactionTypeSchema.default('like'),
});

export const SendMessagePayloadSchema = z.object({
  type: z.literal('send_message'),
  /** Messenger thread id or profile id of the recipient. */
  threadId: z.string().min(1).max(128),
  text: z.string().min(1).max(20_000),
  media: z.array(MediaRefSchema).max(10).default([]),
});

/** The complete set of actions the automation engine can execute. */
export const AutomationActionSchema = z.discriminatedUnion('type', [
  CreatePostPayloadSchema,
  UploadMediaPayloadSchema,
  CommentPayloadSchema,
  ReactToPostPayloadSchema,
  SendMessagePayloadSchema,
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
