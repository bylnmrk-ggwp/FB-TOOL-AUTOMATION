import { z } from 'zod';
import { IdSchema, IsoDateTimeSchema } from './common.js';
import { AccountSchema, AccountStatusSchema, BrowserSessionSchema } from './account.js';
import { JobSchema, QueueStatsSchema } from './job.js';
import { LogEntrySchema } from './log.js';
import { OperatorRequestSchema } from './input.js';

/** Envelope shared by every server-to-client message. */
const event = <T extends string, P extends z.ZodTypeAny>(type: T, payload: P) =>
  z.object({
    type: z.literal(type),
    timestamp: IsoDateTimeSchema,
    payload,
  });

export const AccountCreatedEvent = event('account.created', AccountSchema);
export const AccountUpdatedEvent = event('account.updated', AccountSchema);
export const AccountDeletedEvent = event('account.deleted', z.object({ accountId: IdSchema }));
export const AccountStatusChangedEvent = event(
  'account.status.changed',
  z.object({
    accountId: IdSchema,
    status: AccountStatusSchema,
    previousStatus: AccountStatusSchema,
    reason: z.string().nullable(),
  }),
);

export const BrowserStartedEvent = event('browser.started', BrowserSessionSchema);
export const BrowserStoppedEvent = event(
  'browser.stopped',
  z.object({ accountId: IdSchema, sessionId: IdSchema, reason: z.string().nullable() }),
);
export const BrowserErrorEvent = event(
  'browser.error',
  z.object({ accountId: IdSchema, code: z.string(), message: z.string() }),
);

export const JobCreatedEvent = event('job.created', JobSchema);
export const JobStartedEvent = event('job.started', JobSchema);
export const JobProgressEvent = event(
  'job.progress',
  z.object({
    jobId: IdSchema,
    accountId: IdSchema,
    progress: z.number().min(0).max(100),
    step: z.string(),
  }),
);
export const JobCompletedEvent = event('job.completed', JobSchema);
export const JobFailedEvent = event('job.failed', JobSchema);
export const JobCancelledEvent = event('job.cancelled', JobSchema);
export const JobRetryingEvent = event(
  'job.retrying',
  z.object({
    jobId: IdSchema,
    accountId: IdSchema,
    retryCount: z.number().int().min(0),
    maxRetries: z.number().int().min(0),
    nextAttemptAt: IsoDateTimeSchema,
  }),
);

export const QueueStatsEvent = event('queue.stats', QueueStatsSchema);
export const LogCreatedEvent = event('log.created', LogEntrySchema);
export const ConnectionReadyEvent = event(
  'connection.ready',
  z.object({ clientId: IdSchema, serverVersion: z.string() }),
);

/** The groups known for an account changed; the list should be refetched. */
export const GroupsChangedEvent = event(
  'groups.changed',
  z.object({ accountId: IdSchema, count: z.number().int().min(0) }),
);

export const InputRequestedEvent = event('input.requested', OperatorRequestSchema);
export const InputResolvedEvent = event(
  'input.resolved',
  z.object({ requestId: IdSchema, jobId: IdSchema, cancelled: z.boolean() }),
);

export const ServerEventSchema = z.discriminatedUnion('type', [
  AccountCreatedEvent,
  AccountUpdatedEvent,
  AccountDeletedEvent,
  AccountStatusChangedEvent,
  BrowserStartedEvent,
  BrowserStoppedEvent,
  BrowserErrorEvent,
  JobCreatedEvent,
  JobStartedEvent,
  JobProgressEvent,
  JobCompletedEvent,
  JobFailedEvent,
  JobCancelledEvent,
  JobRetryingEvent,
  QueueStatsEvent,
  LogCreatedEvent,
  ConnectionReadyEvent,
  GroupsChangedEvent,
  InputRequestedEvent,
  InputResolvedEvent,
]);
export type ServerEvent = z.infer<typeof ServerEventSchema>;
export type ServerEventType = ServerEvent['type'];

export type ServerEventOf<T extends ServerEventType> = Extract<ServerEvent, { type: T }>;

/** Messages the browser may send. Kept minimal on purpose: the socket is read-mostly. */
export const ClientMessageSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('ping') }),
  z.object({ type: z.literal('subscribe'), payload: z.object({ topics: z.array(z.string()) }) }),
]);
export type ClientMessage = z.infer<typeof ClientMessageSchema>;
