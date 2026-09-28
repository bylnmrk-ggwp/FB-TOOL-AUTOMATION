import { describe, expect, it } from 'vitest';
import {
  canTransitionAccount,
  canTransitionJob,
  classifyError,
  compareQueueOrder,
  hasRetriesLeft,
  isAccountAvailable,
  isBrowserRunning,
  isCancellable,
  isDue,
  isLockExpired,
  isRetriable,
  isTerminalJobStatus,
  nextAttemptAt,
} from '@fb/domain';
import {
  AutomationTimeoutError,
  NotLoggedInError,
  backoffDelayMs,
  randomDelayMs,
  redact,
  slugify,
  validateSettings,
  DEFAULT_SETTINGS,
  type Job,
} from '@fb/shared';

const job = (overrides: Partial<Job> = {}): Job => ({
  id: 'job_1',
  accountId: 'acc_1',
  type: 'create_post',
  status: 'pending',
  payload: { type: 'create_post', text: 'hello', media: [], audience: 'friends' },
  priority: 0,
  retryCount: 0,
  maxRetries: 2,
  progress: 0,
  runAfter: null,
  result: null,
  lastError: null,
  createdAt: '2026-01-01T00:00:00.000Z',
  queuedAt: null,
  startedAt: null,
  finishedAt: null,
  updatedAt: '2026-01-01T00:00:00.000Z',
  ...overrides,
});

describe('account status machine', () => {
  it('allows the ordinary start and stop path', () => {
    expect(canTransitionAccount('offline', 'starting')).toBe(true);
    expect(canTransitionAccount('starting', 'online')).toBe(true);
    expect(canTransitionAccount('online', 'busy')).toBe(true);
    expect(canTransitionAccount('busy', 'online')).toBe(true);
    expect(canTransitionAccount('online', 'stopping')).toBe(true);
    expect(canTransitionAccount('stopping', 'offline')).toBe(true);
  });

  it('refuses to skip the starting step', () => {
    expect(canTransitionAccount('offline', 'online')).toBe(false);
    expect(canTransitionAccount('offline', 'busy')).toBe(false);
  });

  it('treats a repeat of the current status as a no-op', () => {
    expect(canTransitionAccount('online', 'online')).toBe(true);
  });

  it('only counts an idle online account as available', () => {
    expect(isAccountAvailable('online')).toBe(true);
    expect(isAccountAvailable('busy')).toBe(false);
    expect(isAccountAvailable('offline')).toBe(false);
  });

  it('knows which statuses imply a live browser', () => {
    expect(isBrowserRunning('starting')).toBe(true);
    expect(isBrowserRunning('online')).toBe(true);
    expect(isBrowserRunning('busy')).toBe(true);
    expect(isBrowserRunning('stopping')).toBe(false);
    expect(isBrowserRunning('offline')).toBe(false);
  });
});

describe('job status machine', () => {
  it('follows the queue lifecycle', () => {
    expect(canTransitionJob('pending', 'queued')).toBe(true);
    expect(canTransitionJob('queued', 'running')).toBe(true);
    expect(canTransitionJob('running', 'completed')).toBe(true);
    expect(canTransitionJob('running', 'retrying')).toBe(true);
    expect(canTransitionJob('retrying', 'queued')).toBe(true);
  });

  it('never leaves a completed job', () => {
    expect(canTransitionJob('completed', 'running')).toBe(false);
    expect(canTransitionJob('completed', 'pending')).toBe(false);
    expect(isTerminalJobStatus('completed')).toBe(true);
  });

  it('allows a cancel from anywhere that is still in flight', () => {
    for (const status of ['pending', 'queued', 'running', 'retrying'] as const) {
      expect(canTransitionJob(status, 'cancelled')).toBe(true);
      expect(isCancellable(status)).toBe(true);
    }
    expect(isCancellable('completed')).toBe(false);
  });

  it('only retries a job that finished unsuccessfully', () => {
    expect(isRetriable('failed')).toBe(true);
    expect(isRetriable('cancelled')).toBe(true);
    expect(isRetriable('completed')).toBe(false);
    expect(isRetriable('running')).toBe(false);
  });
});

describe('job scheduling helpers', () => {
  it('stops retrying once the attempts are used up', () => {
    expect(hasRetriesLeft(job({ retryCount: 1, maxRetries: 2 }))).toBe(true);
    expect(hasRetriesLeft(job({ retryCount: 2, maxRetries: 2 }))).toBe(false);
  });

  it('does not retry an error marked non-retryable', () => {
    const error = {
      code: 'AUTOMATION_NOT_LOGGED_IN',
      message: 'not logged in',
      retryable: false,
      occurredAt: '2026-01-01T00:00:00.000Z',
    };
    expect(hasRetriesLeft(job({ retryCount: 0, maxRetries: 3, lastError: error }))).toBe(false);
  });

  it('treats a job with no schedule as due', () => {
    expect(isDue(job(), new Date())).toBe(true);
  });

  it('holds a job scheduled for later', () => {
    const later = new Date(Date.now() + 60_000).toISOString();
    expect(isDue(job({ runAfter: later }), new Date())).toBe(false);
  });

  it('backs the next attempt off into the future', () => {
    const now = new Date('2026-01-01T00:00:00.000Z');
    const next = nextAttemptAt(job({ retryCount: 1 }), now, 10_000);
    expect(next.getTime()).toBeGreaterThan(now.getTime());
  });

  it('orders by priority first and age second', () => {
    const older = job({ id: 'a', createdAt: '2026-01-01T00:00:00.000Z' });
    const newer = job({ id: 'b', createdAt: '2026-01-02T00:00:00.000Z' });
    const urgent = job({ id: 'c', priority: 10, createdAt: '2026-01-03T00:00:00.000Z' });

    const ordered = [newer, older, urgent].sort(compareQueueOrder).map((entry) => entry.id);
    expect(ordered).toEqual(['c', 'a', 'b']);
  });
});

describe('error classification', () => {
  it('keeps the retryable flag of a known automation error', () => {
    const timeout = classifyError(new AutomationTimeoutError('open composer', 30_000));
    expect(timeout.retryable).toBe(true);
    expect(timeout.code).toBe('AUTOMATION_TIMEOUT');
  });

  it('refuses to retry a login problem', () => {
    expect(classifyError(new NotLoggedInError('acc_1')).retryable).toBe(false);
  });

  it('treats an unknown failure as worth one more attempt', () => {
    expect(classifyError(new Error('socket hang up')).retryable).toBe(true);
    expect(classifyError('something odd').retryable).toBe(true);
  });
});

describe('lock expiry', () => {
  it('expires a lock older than the TTL', () => {
    const acquired = new Date('2026-01-01T00:00:00.000Z');
    const later = new Date(acquired.getTime() + 61_000);
    expect(isLockExpired(acquired, later, 60_000)).toBe(true);
    expect(isLockExpired(acquired, new Date(acquired.getTime() + 30_000), 60_000)).toBe(false);
  });
});

describe('shared utilities', () => {
  it('removes credential-shaped values at any depth', () => {
    const redacted = redact({
      accountId: 'acc_1',
      password: 'hunter2',
      nested: { sessionToken: 'abc', cookies: ['a'], keep: 1 },
    }) as Record<string, unknown>;

    expect(redacted['accountId']).toBe('acc_1');
    expect(redacted['password']).toBe('[redacted]');
    expect(redacted['nested']).toMatchObject({
      sessionToken: '[redacted]',
      cookies: '[redacted]',
      keep: 1,
    });
  });

  it('turns a display name into a filesystem-safe slug', () => {
    expect(slugify('Marketing One')).toBe('marketing-one');
    expect(slugify('  Ünïcode!!  ')).toBe('unicode');
    expect(slugify('a')).toMatch(/^account-[a-z0-9]{4}$/);
  });

  it('keeps backoff inside its bounds', () => {
    for (let attempt = 1; attempt <= 10; attempt += 1) {
      const delay = backoffDelayMs(attempt, 1_000, 60_000);
      expect(delay).toBeGreaterThan(0);
      expect(delay).toBeLessThanOrEqual(60_000);
    }
  });

  it('keeps a random pause inside its range', () => {
    for (let i = 0; i < 50; i += 1) {
      const delay = randomDelayMs(100, 200);
      expect(delay).toBeGreaterThanOrEqual(100);
      expect(delay).toBeLessThanOrEqual(200);
    }
  });

  it('catches settings that contradict each other', () => {
    expect(validateSettings(DEFAULT_SETTINGS)).toEqual([]);
    expect(
      validateSettings({ ...DEFAULT_SETTINGS, minActionDelayMs: 5_000, maxActionDelayMs: 1_000 }),
    ).toHaveLength(1);
  });
});
