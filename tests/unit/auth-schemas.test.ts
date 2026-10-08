import { describe, expect, it } from 'vitest';
import {
  AuthInvalidError,
  AuthRateLimitedError,
  AuthRequiredError,
  AuthSessionSchema,
  ERROR_CODES,
  LoginRequestSchema,
  LoginResponseSchema,
} from '@fb/shared';

describe('auth errors', () => {
  it('map to the HTTP statuses the guard relies on', () => {
    expect(new AuthRequiredError()).toMatchObject({ code: ERROR_CODES.AUTH_REQUIRED, status: 401 });
    expect(new AuthInvalidError()).toMatchObject({ code: ERROR_CODES.AUTH_INVALID, status: 401 });
    expect(new AuthRateLimitedError(120)).toMatchObject({
      code: ERROR_CODES.AUTH_RATE_LIMITED,
      status: 429,
      details: { retryAfterSeconds: 120 },
    });
  });
});

describe('auth schemas', () => {
  it('requires a non-empty password', () => {
    expect(LoginRequestSchema.safeParse({ password: '' }).success).toBe(false);
    expect(LoginRequestSchema.safeParse({}).success).toBe(false);
    expect(LoginRequestSchema.safeParse({ password: 'hunter22' }).success).toBe(true);
  });

  it('describes the login response and the session probe', () => {
    expect(
      LoginResponseSchema.safeParse({ token: 'v1.1.abc', expiresAt: '2026-11-07T00:00:00.000Z' })
        .success,
    ).toBe(true);
    expect(AuthSessionSchema.parse({ authRequired: true, authenticated: false })).toEqual({
      authRequired: true,
      authenticated: false,
    });
  });
});
