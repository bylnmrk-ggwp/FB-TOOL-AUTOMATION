import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ERROR_CODES, LoginResponseSchema } from '@fb/shared';
import { createTestServer, type TestServer } from '../helpers/server';

const PASSWORD = 'hunter22';

describe('Auth API with the login off', () => {
  let server: TestServer;

  beforeEach(async () => {
    server = await createTestServer();
  });

  afterEach(async () => {
    await server.dispose();
  });

  it('reports that no login is needed and leaves every route open', async () => {
    const session = await server.app.inject({ method: 'GET', url: '/api/v1/auth/session' });
    expect(session.statusCode).toBe(200);
    expect(session.json()).toEqual({ authRequired: false, authenticated: true });

    const accounts = await server.app.inject({ method: 'GET', url: '/api/v1/accounts' });
    expect(accounts.statusCode).toBe(200);
  });

  it('refuses to log in when there is no password to check against', async () => {
    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { password: 'anything' },
    });
    expect(response.statusCode).toBe(409);
    expect(response.json().error.code).toBe(ERROR_CODES.CONFLICT);
  });
});

describe('Auth API with the login on', () => {
  let server: TestServer;

  beforeEach(async () => {
    server = await createTestServer({ auth: { password: PASSWORD } });
  });

  afterEach(async () => {
    await server.dispose();
  });

  const login = (password: string) =>
    server.app.inject({ method: 'POST', url: '/api/v1/auth/login', payload: { password } });

  it('gates the API but not health, the session probe, or the page', async () => {
    const accounts = await server.app.inject({ method: 'GET', url: '/api/v1/accounts' });
    expect(accounts.statusCode).toBe(401);
    expect(accounts.json().error.code).toBe(ERROR_CODES.AUTH_REQUIRED);

    expect((await server.app.inject({ method: 'GET', url: '/api/v1/health' })).statusCode).toBe(200);

    const session = await server.app.inject({ method: 'GET', url: '/api/v1/auth/session' });
    expect(session.json()).toEqual({ authRequired: true, authenticated: false });

    // No build in the test directory, so the page is a 404, but it is the
    // JSON 404 of a route that was reached, not a 401 from the guard.
    expect((await server.app.inject({ method: 'GET', url: '/' })).statusCode).toBe(404);
    expect((await server.app.inject({ method: 'GET', url: '/assets/app.js' })).statusCode).toBe(404);
    expect(
      (await server.app.inject({ method: 'OPTIONS', url: '/api/v1/accounts' })).statusCode,
    ).not.toBe(401);
  });

  it('treats a malformed Authorization header as no token', async () => {
    for (const authorization of ['Basic abc', 'Bearer', 'Bearer ', 'bearer v1.1.x', 'v1.1.x']) {
      const response = await server.app.inject({
        method: 'GET',
        url: '/api/v1/accounts',
        headers: { authorization },
      });
      expect(response.statusCode, authorization).toBe(401);
      expect(response.json().error.code).toBe(ERROR_CODES.AUTH_REQUIRED);
    }
  });

  it('rejects a wrong password and accepts the right one', async () => {
    const wrong = await login('nope');
    expect(wrong.statusCode).toBe(401);
    expect(wrong.json().error.code).toBe(ERROR_CODES.AUTH_INVALID);

    const right = await login(PASSWORD);
    expect(right.statusCode).toBe(200);
    const { token, expiresAt } = LoginResponseSchema.parse(right.json());
    expect(Date.parse(expiresAt)).toBeGreaterThan(Date.now());

    const accounts = await server.app.inject({
      method: 'GET',
      url: '/api/v1/accounts',
      headers: { authorization: `Bearer ${token}` },
    });
    expect(accounts.statusCode).toBe(200);

    const session = await server.app.inject({
      method: 'GET',
      url: '/api/v1/auth/session',
      headers: { authorization: `Bearer ${token}` },
    });
    expect(session.json()).toEqual({ authRequired: true, authenticated: true });
  });

  it('does not count an invalid body as a failed attempt', async () => {
    for (let i = 0; i < 5; i += 1) {
      const response = await server.app.inject({
        method: 'POST',
        url: '/api/v1/auth/login',
        payload: { password: '' },
      });
      expect(response.statusCode).toBe(400);
      expect(response.json().error.code).toBe(ERROR_CODES.VALIDATION_ERROR);
    }
    expect((await login(PASSWORD)).statusCode).toBe(200);
  });

  it('locks the login after five wrong passwords and frees it on a right one later', async () => {
    for (let i = 0; i < 5; i += 1) expect((await login('nope')).statusCode).toBe(401);

    const locked = await login(PASSWORD);
    expect(locked.statusCode).toBe(429);
    expect(locked.json().error.code).toBe(ERROR_CODES.AUTH_RATE_LIMITED);
    expect(locked.json().error.details.retryAfterSeconds).toBeGreaterThan(0);
  });

  it('rejects a token signed with another secret', async () => {
    const other = await createTestServer({ auth: { password: PASSWORD, secret: 'other-secret' } });
    try {
      const foreign = LoginResponseSchema.parse(
        (
          await other.app.inject({
            method: 'POST',
            url: '/api/v1/auth/login',
            payload: { password: PASSWORD },
          })
        ).json(),
      ).token;

      const response = await server.app.inject({
        method: 'GET',
        url: '/api/v1/accounts',
        headers: { authorization: `Bearer ${foreign}` },
      });
      expect(response.statusCode).toBe(401);
    } finally {
      await other.dispose();
    }
  });
});
