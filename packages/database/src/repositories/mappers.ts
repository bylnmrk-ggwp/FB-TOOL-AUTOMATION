import {
  AutomationActionSchema,
  AutomationResultSchema,
  JobErrorSchema,
  type Account,
  type AutomationAction,
  type AutomationResult,
  type BrowserProfile,
  type Job,
  type JobError,
  type LogEntry,
} from '@fb/shared';
import type { AccountRow } from '../schema/accounts.js';
import type { BrowserProfileRow } from '../schema/browserProfiles.js';
import type { JobRow } from '../schema/jobs.js';
import type { AutomationLogRow } from '../schema/logs.js';

/**
 * Rows become domain objects here and nowhere else. JSON columns are parsed
 * through the shared schema, so a row written by an older version fails loudly
 * instead of flowing on as a half-filled object.
 */
export const toAccount = (row: AccountRow): Account => ({
  id: row.id,
  name: row.name,
  displayName: row.displayName,
  profileId: row.profileId,
  status: row.status,
  enabled: row.enabled,
  lastError: row.lastError,
  lastActiveAt: row.lastActiveAt,
  createdAt: row.createdAt,
  updatedAt: row.updatedAt,
});

export const toBrowserProfile = (row: BrowserProfileRow): BrowserProfile => ({
  id: row.id,
  accountId: row.accountId,
  slug: row.slug,
  directory: row.directory,
  channel: row.channel,
  lockedBy: row.lockedBy,
  lockedAt: row.lockedAt,
  lastUsedAt: row.lastUsedAt,
  createdAt: row.createdAt,
  updatedAt: row.updatedAt,
});

const parseJson = <T>(value: string | null, parse: (input: unknown) => T, column: string): T => {
  if (value === null) throw new Error(`Column ${column} is unexpectedly null`);
  let raw: unknown;
  try {
    raw = JSON.parse(value);
  } catch (error) {
    throw new Error(`Column ${column} does not hold valid JSON`, { cause: error });
  }
  return parse(raw);
};

export const toJob = (row: JobRow): Job => ({
  id: row.id,
  accountId: row.accountId,
  type: row.type,
  status: row.status,
  payload: parseJson<AutomationAction>(
    row.payload,
    (input) => AutomationActionSchema.parse(input),
    'jobs.payload',
  ),
  priority: row.priority,
  retryCount: row.retryCount,
  maxRetries: row.maxRetries,
  progress: row.progress,
  runAfter: row.runAfter,
  result:
    row.result === null
      ? null
      : parseJson<AutomationResult>(
          row.result,
          (input) => AutomationResultSchema.parse(input),
          'jobs.result',
        ),
  lastError:
    row.lastError === null
      ? null
      : parseJson<JobError>(
          row.lastError,
          (input) => JobErrorSchema.parse(input),
          'jobs.last_error',
        ),
  createdAt: row.createdAt,
  queuedAt: row.queuedAt,
  startedAt: row.startedAt,
  finishedAt: row.finishedAt,
  updatedAt: row.updatedAt,
});

export const toLogEntry = (row: AutomationLogRow): LogEntry => ({
  id: row.id,
  level: row.level,
  message: row.message,
  event: row.event,
  accountId: row.accountId,
  jobId: row.jobId,
  sessionId: row.sessionId,
  requestId: row.requestId,
  context: row.context === null ? null : (JSON.parse(row.context) as Record<string, unknown>),
  createdAt: row.createdAt,
});

export const toJsonColumn = (value: unknown): string => JSON.stringify(value);
