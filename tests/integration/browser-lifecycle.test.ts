import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ERROR_CODES } from '@fb/shared';
import { createTestServer, type TestServer } from '../helpers/server';

describe('Browser lifecycle', () => {
  let server: TestServer;
  let accountId: string;

  beforeEach(async () => {
    server = await createTestServer();
    const created = await server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name: 'Alpha' },
    });
    accountId = created.json().id;
  });

  afterEach(async () => {
    await server.dispose();
  });

  const start = () =>
    server.app.inject({ method: 'POST', url: `/api/v1/accounts/${accountId}/browser/start` });

  const stop = () =>
    server.app.inject({ method: 'POST', url: `/api/v1/accounts/${accountId}/browser/stop` });

  const profileId = async (): Promise<string> => {
    const profile = await server.container.repositories.profiles.findByAccountId(accountId);
    if (profile === null) throw new Error('missing profile');
    return profile.id;
  };

  it('starts a browser, marks the account online and holds the profile lock', async () => {
    const response = await start();

    expect(response.statusCode).toBe(202);
    expect(response.json().accountId).toBe(accountId);

    const account = await server.container.repositories.accounts.findById(accountId);
    expect(account?.status).toBe('online');
    expect(await server.container.locks.isLocked(await profileId())).toBe(true);
    expect(existsSync(join(server.directory, 'browser-profiles', 'alpha'))).toBe(true);
  });

  it('announces the start over the event bus', async () => {
    await start();

    const started = server.events.filter((event) => event.type === 'browser.started');
    const statuses = server.events.filter((event) => event.type === 'account.status.changed');

    expect(started).toHaveLength(1);
    expect(statuses.map((event) => event.payload.status)).toEqual(['starting', 'online']);
  });

  it('refuses a second browser for the same account', async () => {
    await start();
    const second = await start();

    expect(second.statusCode).toBe(409);
    expect(second.json().error.code).toBe(ERROR_CODES.BROWSER_ALREADY_RUNNING);
  });

  it('refuses to start a disabled account', async () => {
    await server.app.inject({ method: 'POST', url: `/api/v1/accounts/${accountId}/disable` });
    const response = await start();

    expect(response.statusCode).toBe(409);
    expect(response.json().error.code).toBe(ERROR_CODES.ACCOUNT_DISABLED);
  });

  it('stops a browser, releases the lock and returns the account to offline', async () => {
    await start();
    const response = await stop();

    expect(response.statusCode).toBe(204);
    expect((await server.container.repositories.accounts.findById(accountId))?.status).toBe(
      'offline',
    );
    expect(await server.container.locks.isLocked(await profileId())).toBe(false);
  });

  it('answers 409 when asked to stop a browser that is not running', async () => {
    const response = await stop();

    expect(response.statusCode).toBe(409);
    expect(response.json().error.code).toBe(ERROR_CODES.BROWSER_NOT_RUNNING);
  });

  it('reports the running session and 404s once it is gone', async () => {
    await start();
    const running = await server.app.inject({
      method: 'GET',
      url: `/api/v1/accounts/${accountId}/browser`,
    });
    expect(running.statusCode).toBe(200);
    expect(running.json().status).toBe('online');

    await stop();
    const gone = await server.app.inject({
      method: 'GET',
      url: `/api/v1/accounts/${accountId}/browser`,
    });
    expect(gone.statusCode).toBe(404);
  });

  it('releases the lock and records the error when a launch fails', async () => {
    server.browser.failNextLaunch = new Error('Chromium is not installed');
    const response = await start();

    expect(response.statusCode).toBe(500);

    const account = await server.container.repositories.accounts.findById(accountId);
    expect(account?.status).toBe('error');
    expect(account?.lastError).toContain('Chromium is not installed');
    expect(await server.container.locks.isLocked(await profileId())).toBe(false);
  });

  it('cleans up after a browser that closes on its own', async () => {
    await start();
    server.browser.simulateCrash(accountId);

    // The close handler runs asynchronously, as it does in production.
    await new Promise((resolve) => setTimeout(resolve, 50));

    const account = await server.container.repositories.accounts.findById(accountId);
    expect(account?.status).toBe('offline');
    expect(await server.container.locks.isLocked(await profileId())).toBe(false);
    expect(server.events.some((event) => event.type === 'browser.stopped')).toBe(true);
  });

  it('lets the account start again after a crash', async () => {
    await start();
    server.browser.simulateCrash(accountId);
    await new Promise((resolve) => setTimeout(resolve, 50));

    const again = await start();
    expect(again.statusCode).toBe(202);
  });

  it('lists every running session', async () => {
    await start();
    const response = await server.app.inject({ method: 'GET', url: '/api/v1/browser/sessions' });

    expect(response.json().sessions).toHaveLength(1);
    expect(response.json().sessions[0].accountId).toBe(accountId);
  });
});
