import { describe, expect, it } from 'vitest';
import { AccountLockManager, RetryManager } from '@fb/queue';
import type { Job, JobError } from '@fb/shared';

const job = (overrides: Partial<Job> = {}): Job => ({
  id: 'job_1',
  accountId: 'acc_1',
  type: 'create_post',
  status: 'running',
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

const error = (retryable: boolean): JobError => ({
  code: retryable ? 'AUTOMATION_TIMEOUT' : 'AUTOMATION_BLOCKED',
  message: 'something happened',
  retryable,
  occurredAt: '2026-01-01T00:00:00.000Z',
});

describe('RetryManager', () => {
  const retries = new RetryManager({ baseDelayMs: 1_000, maxDelayMs: 60_000 });
  const now = new Date('2026-01-01T00:00:00.000Z');

  it('retries a retryable error while attempts remain', () => {
    const decision = retries.decide(job({ retryCount: 0, maxRetries: 2 }), error(true), now);

    expect(decision.retry).toBe(true);
    expect(decision.nextAttemptAt).not.toBeNull();
    expect(decision.nextAttemptAt!.getTime()).toBeGreaterThan(now.getTime());
  });

  it('never retries an error marked non-retryable, however many attempts are left', () => {
    const decision = retries.decide(job({ retryCount: 0, maxRetries: 10 }), error(false), now);

    expect(decision.retry).toBe(false);
    expect(decision.nextAttemptAt).toBeNull();
  });

  it('stops once the attempts are used up', () => {
    const decision = retries.decide(job({ retryCount: 2, maxRetries: 2 }), error(true), now);

    expect(decision.retry).toBe(false);
    expect(decision.reason).toContain('No attempts left');
  });

  it('waits longer after each attempt', () => {
    const first = retries.decide(job({ retryCount: 0 }), error(true), now);
    const later = retries.decide(job({ retryCount: 4, maxRetries: 9 }), error(true), now);

    const firstDelay = first.nextAttemptAt!.getTime() - now.getTime();
    const laterDelay = later.nextAttemptAt!.getTime() - now.getTime();
    expect(laterDelay).toBeGreaterThan(firstDelay);
  });

  it('never waits longer than the ceiling', () => {
    const decision = retries.decide(job({ retryCount: 20, maxRetries: 30 }), error(true), now);
    expect(decision.nextAttemptAt!.getTime() - now.getTime()).toBeLessThanOrEqual(60_000);
  });
});

describe('AccountLockManager', () => {
  it('grants an account to one job at a time', () => {
    const locks = new AccountLockManager();

    expect(locks.tryAcquire('acc_1', 'job_1')).toBe(true);
    expect(locks.tryAcquire('acc_1', 'job_2')).toBe(false);
    expect(locks.jobHolding('acc_1')).toBe('job_1');
  });

  it('lets a different account run at the same time', () => {
    const locks = new AccountLockManager();

    expect(locks.tryAcquire('acc_1', 'job_1')).toBe(true);
    expect(locks.tryAcquire('acc_2', 'job_2')).toBe(true);
    expect(locks.size()).toBe(2);
  });

  it('frees the account when the job finishes', () => {
    const locks = new AccountLockManager();

    locks.tryAcquire('acc_1', 'job_1');
    locks.release('acc_1');

    expect(locks.isHeld('acc_1')).toBe(false);
    expect(locks.tryAcquire('acc_1', 'job_2')).toBe(true);
  });

  it('reports which accounts are busy, so the claim query can skip them', () => {
    const locks = new AccountLockManager();

    locks.tryAcquire('acc_1', 'job_1');
    locks.tryAcquire('acc_2', 'job_2');

    expect(locks.heldAccountIds().sort()).toEqual(['acc_1', 'acc_2']);
  });
});
