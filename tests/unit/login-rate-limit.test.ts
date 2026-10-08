import { describe, expect, it } from 'vitest';
import { LoginRateLimiter } from '../../apps/server/dist/http/auth/rate-limit.js';
import { passwordMatches } from '../../apps/server/dist/http/auth/password.js';

const MINUTE = 60_000;

describe('LoginRateLimiter', () => {
  it('allows four failures and blocks on the fifth', () => {
    const limiter = new LoginRateLimiter();
    for (let i = 0; i < 4; i += 1) limiter.recordFailure(i * 1_000);
    expect(limiter.isLimited(5_000)).toBe(false);
    limiter.recordFailure(5_000);
    expect(limiter.isLimited(6_000)).toBe(true);
  });

  it('frees up once the oldest failure leaves the window', () => {
    const limiter = new LoginRateLimiter({ limit: 2, windowMs: 15 * MINUTE });
    limiter.recordFailure(0);
    limiter.recordFailure(MINUTE);
    expect(limiter.isLimited(2 * MINUTE)).toBe(true);
    expect(limiter.retryAfterMs(2 * MINUTE)).toBe(13 * MINUTE);
    expect(limiter.isLimited(15 * MINUTE)).toBe(false);
  });

  it('resets on a successful login', () => {
    const limiter = new LoginRateLimiter({ limit: 1 });
    limiter.recordFailure(0);
    expect(limiter.isLimited(1)).toBe(true);
    limiter.reset();
    expect(limiter.isLimited(2)).toBe(false);
    expect(limiter.retryAfterMs(2)).toBe(0);
  });
});

describe('passwordMatches', () => {
  it('compares exactly, including length', () => {
    expect(passwordMatches('hunter22', 'hunter22')).toBe(true);
    expect(passwordMatches('hunter2', 'hunter22')).toBe(false);
    expect(passwordMatches('hunter22 ', 'hunter22')).toBe(false);
    expect(passwordMatches('', 'hunter22')).toBe(false);
  });
});
