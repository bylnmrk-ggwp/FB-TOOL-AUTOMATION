import { z } from 'zod';
import { INPUT_KINDS } from '../constants/index.js';
import { CoercedDateTimeSchema, IdSchema } from './common.js';

export const InputKindSchema = z.enum(INPUT_KINDS);
export type InputKind = z.infer<typeof InputKindSchema>;

/**
 * A job has stopped and needs a person: a picture challenge to solve in the
 * browser window, a code to type, a checkpoint to clear. The prompt says what
 * is wanted and the job waits, up to its timeout, for an answer.
 */
export const OperatorRequestSchema = z.object({
  id: IdSchema,
  jobId: IdSchema,
  accountId: IdSchema,
  kind: InputKindSchema,
  message: z.string(),
  /** Whether typing something back is expected, or only confirming it is done. */
  expectsText: z.boolean(),
  createdAt: CoercedDateTimeSchema,
  expiresAt: CoercedDateTimeSchema,
});
export type OperatorRequest = z.infer<typeof OperatorRequestSchema>;

export const AnswerOperatorRequestSchema = z.object({
  requestId: IdSchema,
  /** The typed answer, or empty when the person only confirms they are done. */
  value: z.string().max(2_000).default(''),
  /** Gives up on the job instead of answering. */
  cancel: z.boolean().default(false),
});
export type AnswerOperatorRequestInput = z.input<typeof AnswerOperatorRequestSchema>;

export const OperatorAnswerSchema = z.object({
  value: z.string(),
  cancelled: z.boolean(),
});
export type OperatorAnswer = z.infer<typeof OperatorAnswerSchema>;
