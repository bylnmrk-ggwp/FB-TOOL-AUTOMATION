export const API_PREFIX = '/api/v1';
export const WEBSOCKET_PATH = '/ws';

/** Lifecycle of a browser session owned by one account. */
export const ACCOUNT_STATUSES = [
  'offline',
  'starting',
  'online',
  'busy',
  'stopping',
  'error',
] as const;

/**
 * What the last login check found. Separate from the browser status: an
 * account can have a browser open and still be signed out, and can be signed
 * in with no browser open at all.
 */
export const LOGIN_STATUSES = [
  'unknown',
  'logged_in',
  'logged_out',
  'checkpoint',
  'two_factor',
  'email_confirmation',
  'captcha',
  'disabled',
  'restricted',
] as const;

/** Lifecycle of a queued automation job. */
export const JOB_STATUSES = [
  'pending',
  'queued',
  'running',
  'retrying',
  'completed',
  'failed',
  'cancelled',
] as const;

/** Job states that are still going to consume a worker slot. */
export const ACTIVE_JOB_STATUSES = ['pending', 'queued', 'running', 'retrying'] as const;

/** Job states that never change again. */
export const TERMINAL_JOB_STATUSES = ['completed', 'failed', 'cancelled'] as const;

export const JOB_TYPES = [
  'create_post',
  'upload_media',
  'comment',
  'react_to_post',
  'send_message',
  'share_post',
  'share_to_group',
  'join_group',
  'fetch_groups',
  'login',
  'check_login',
  'accept_friend_requests',
  'add_friends',
  'auto_setup_profile',
  'watch_live',
] as const;

export const LOG_LEVELS = ['debug', 'info', 'warn', 'error'] as const;

export const REACTION_TYPES = ['like', 'love', 'care', 'haha', 'wow', 'sad', 'angry'] as const;

export const POST_AUDIENCES = ['public', 'friends', 'only_me'] as const;

/** Where a shared post lands. `feed` goes through the full composer. */
export const SHARE_TARGETS = ['timeline', 'story', 'feed'] as const;

export const BROWSER_CHANNELS = ['chromium', 'chrome', 'msedge', 'brave'] as const;

/** What the automation can stop and ask a person for. */
export const INPUT_KINDS = ['captcha', 'two_factor', 'checkpoint', 'confirm', 'text'] as const;

export const ACTIVITY_KINDS = ['share', 'join', 'comment', 'react'] as const;

export const DEFAULTS = {
  jobPriority: 0,
  maxRetries: 2,
  globalConcurrency: 2,
  timeoutMs: 30_000,
  /** A running job untouched for this long is treated as abandoned on startup. */
  staleJobTimeoutMs: 900_000,
  /** A profile lock older than this is stale and may be broken. */
  profileLockTtlMs: 300_000,
  retryBackoffMs: 5_000,
  retryBackoffMaxMs: 300_000,
  logPageSize: 100,
  /** How long a job waits for a person before it gives up. */
  operatorInputTimeoutMs: 180_000,
} as const;

export const PRIORITY_RANGE = { min: -100, max: 100 } as const;
