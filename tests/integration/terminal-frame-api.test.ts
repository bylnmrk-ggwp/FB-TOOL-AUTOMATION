import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ERROR_CODES, unpackTerminalFrame } from '@fb/shared';
import { createTestServer, type TestServer } from '../helpers/server';

describe('Terminal frame API', () => {
  let server: TestServer;

  afterEach(async () => {
    await server.dispose();
  });

  const createAccount = async (): Promise<string> => {
    const created = await server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name: 'Terminal One' },
    });
    return (created.json() as { id: string }).id;
  };

  describe('with the login off', () => {
    beforeEach(async () => {
      server = await createTestServer();
    });

    it('says so when the account has no browser open', async () => {
      const id = await createAccount();
      const response = await server.app.inject({
        method: 'GET',
        url: `/api/v1/accounts/${id}/browser/terminal`,
      });

      expect(response.statusCode).toBe(404);
      expect(response.json().error.code).toBe(ERROR_CODES.BROWSER_NOT_RUNNING);
    });

    it('serves the running browser as a packed frame that is never cached', async () => {
      const id = await createAccount();
      await server.app.inject({ method: 'POST', url: `/api/v1/accounts/${id}/browser/start` });

      const response = await server.app.inject({
        method: 'GET',
        url: `/api/v1/accounts/${id}/browser/terminal`,
      });

      expect(response.statusCode).toBe(200);
      expect(response.headers['content-type']).toBe('application/octet-stream');
      expect(response.headers['cache-control']).toBe('no-store');

      const frame = unpackTerminalFrame(new Uint8Array(response.rawPayload));
      expect(frame).toMatchObject({ width: 2, height: 2 });
      // The fake browser shows red, green, blue and white.
      expect([...(frame?.rgba ?? [])].slice(0, 8)).toEqual([255, 0, 0, 255, 0, 255, 0, 255]);
    });
  });

  describe('with the login on', () => {
    beforeEach(async () => {
      server = await createTestServer({ auth: { password: 'hunter22' } });
    });

    it('asks for a token like every other API route', async () => {
      const response = await server.app.inject({
        method: 'GET',
        url: '/api/v1/accounts/acc_anything/browser/terminal',
      });

      expect(response.statusCode).toBe(401);
      expect(response.json().error.code).toBe(ERROR_CODES.AUTH_REQUIRED);
    });
  });
});
