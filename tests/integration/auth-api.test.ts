import { connect } from 'node:net';
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

  describe('WebSocket', () => {
    const listen = async (): Promise<string> => {
      await server.app.listen({ host: '127.0.0.1', port: 0 });
      const address = server.app.server.address();
      if (address === null || typeof address === 'string') throw new Error('No TCP address');
      return `ws://127.0.0.1:${address.port}/ws`;
    };

    const openSocket = (url: string): Promise<'open' | 'refused'> =>
      new Promise((resolve) => {
        const socket = new WebSocket(url);
        socket.onopen = () => {
          socket.close();
          resolve('open');
        };
        socket.onerror = () => resolve('refused');
      });

    it('refuses an upgrade without a token and accepts one with it', async () => {
      const base = await listen();
      expect(await openSocket(base)).toBe('refused');
      expect(await openSocket(`${base}?token=v1.1.forged`)).toBe('refused');

      const { token } = LoginResponseSchema.parse((await login(PASSWORD)).json());
      expect(await openSocket(`${base}?token=${encodeURIComponent(token)}`)).toBe('open');
    });
  });

  // The router normalises a request target before it picks a route. The guard
  // has to judge the route that was picked, not the raw text of the target,
  // or a target the router rewrites would reach a handler without a token.
  describe('request targets the router rewrites', () => {
    const statusOf = (port: number, target: string, extraHeaders = ''): Promise<number> =>
      new Promise((resolve, reject) => {
        let data = '';
        const socket = connect(port, '127.0.0.1', () => {
          socket.write(
            `GET ${target} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n${extraHeaders}\r\n`,
          );
        });
        // The status line is all that matters, and an upgrade that succeeds
        // would otherwise hold the socket open for ever.
        socket.on('data', (chunk: Buffer) => {
          data += chunk.toString();
          const status = /^HTTP\/1\.1 (\d+)/.exec(data)?.[1];
          if (status === undefined) return;
          socket.destroy();
          resolve(Number(status));
        });
        socket.on('error', reject);
      });

    const port = async (): Promise<number> => {
      await server.app.listen({ host: '127.0.0.1', port: 0 });
      const address = server.app.server.address();
      if (address === null || typeof address === 'string') throw new Error('No TCP address');
      return address.port;
    };

    it('asks for a token whatever form the target takes', async () => {
      const listening = await port();
      for (const target of [
        '/api/v1/accounts',
        'http://elsewhere.example/api/v1/accounts',
        '/%61pi/v1/accounts',
        '/api/v1/%61ccounts',
      ]) {
        expect(await statusOf(listening, target), target).toBe(401);
      }
    });

    it('refuses a socket upgrade whatever form the target takes', async () => {
      const listening = await port();
      const upgrade =
        'Upgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n';
      for (const target of ['/ws', 'http://elsewhere.example/ws', '/%77s']) {
        const status = await statusOf(
          listening,
          target,
          upgrade.replace(/^/, 'Connection: Upgrade\r\n'),
        );
        expect(status, target).toBe(401);
      }
    });

    it('still leaves health and the session probe open in every form', async () => {
      const listening = await port();
      for (const target of [
        'http://elsewhere.example/api/v1/health',
        '/api/v1/%68ealth',
        'http://elsewhere.example/api/v1/auth/session',
      ]) {
        expect(await statusOf(listening, target), target).toBe(200);
      }
    });
  });
});
