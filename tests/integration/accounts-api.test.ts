import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { AccountSchema, ERROR_CODES, type Account } from '@fb/shared';
import { createTestServer, type TestServer } from '../helpers/server';

describe('Accounts API', () => {
  let server: TestServer;

  beforeEach(async () => {
    server = await createTestServer();
  });

  afterEach(async () => {
    await server.dispose();
  });

  const createAccount = async (name: string, body: Record<string, unknown> = {}) =>
    server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name, ...body },
    });

  it('reports itself healthy once the database is migrated', async () => {
    const response = await server.app.inject({ method: 'GET', url: '/api/v1/health' });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ status: 'ok', checks: { database: 'up' } });
  });

  it('creates an account and its profile directory', async () => {
    const response = await createAccount('Marketing One');

    expect(response.statusCode).toBe(201);
    const account = AccountSchema.parse(response.json());
    expect(account.name).toBe('Marketing One');
    expect(account.status).toBe('offline');
    expect(account.enabled).toBe(true);

    const profile = await server.container.repositories.profiles.findByAccountId(account.id);
    expect(profile?.slug).toBe('marketing-one');
    expect(existsSync(join(server.directory, 'browser-profiles', 'marketing-one'))).toBe(true);
  });

  it('gives a second account with the same display name its own profile slug', async () => {
    await createAccount('Marketing');
    await createAccount('marketing!');

    const page = await server.container.repositories.accounts.list({ limit: 10, offset: 0 });
    const slugs = await Promise.all(
      page.items.map(async (account) => {
        const profile = await server.container.repositories.profiles.findByAccountId(account.id);
        return profile?.slug;
      }),
    );

    expect(new Set(slugs).size).toBe(2);
  });

  it('refuses a duplicate name with a typed error', async () => {
    await createAccount('Duplicate');
    const response = await createAccount('Duplicate');

    expect(response.statusCode).toBe(409);
    expect(response.json().error.code).toBe(ERROR_CODES.ACCOUNT_NAME_TAKEN);
  });

  it('rejects an empty name before it reaches the database', async () => {
    const response = await createAccount('');

    expect(response.statusCode).toBe(400);
    expect(response.json().error.code).toBe(ERROR_CODES.VALIDATION_ERROR);
  });

  it('lists, searches and paginates', async () => {
    await createAccount('Alpha');
    await createAccount('Beta');
    await createAccount('Gamma');

    const all = await server.app.inject({ method: 'GET', url: '/api/v1/accounts' });
    expect(all.json().total).toBe(3);

    const searched = await server.app.inject({
      method: 'GET',
      url: '/api/v1/accounts?search=Bet',
    });
    expect(searched.json().items.map((account: Account) => account.name)).toEqual(['Beta']);

    const paged = await server.app.inject({ method: 'GET', url: '/api/v1/accounts?limit=2' });
    expect(paged.json().items).toHaveLength(2);
    expect(paged.json().total).toBe(3);
  });

  it('reads one account and answers 404 for an unknown id', async () => {
    const created = await createAccount('Alpha');
    const id = created.json().id;

    const found = await server.app.inject({ method: 'GET', url: `/api/v1/accounts/${id}` });
    expect(found.statusCode).toBe(200);
    expect(found.json().id).toBe(id);

    const missing = await server.app.inject({ method: 'GET', url: '/api/v1/accounts/acc_nope' });
    expect(missing.statusCode).toBe(404);
    expect(missing.json().error.code).toBe(ERROR_CODES.ACCOUNT_NOT_FOUND);
  });

  it('updates an account', async () => {
    const created = await createAccount('Alpha');
    const id = created.json().id;

    const response = await server.app.inject({
      method: 'PATCH',
      url: `/api/v1/accounts/${id}`,
      payload: { displayName: 'Alpha Renamed' },
    });

    expect(response.statusCode).toBe(200);
    expect(response.json().displayName).toBe('Alpha Renamed');
  });

  it('rejects an empty update', async () => {
    const created = await createAccount('Alpha');
    const response = await server.app.inject({
      method: 'PATCH',
      url: `/api/v1/accounts/${created.json().id}`,
      payload: {},
    });

    expect(response.statusCode).toBe(400);
  });

  it('enables and disables an account', async () => {
    const created = await createAccount('Alpha');
    const id = created.json().id;

    const disabled = await server.app.inject({
      method: 'POST',
      url: `/api/v1/accounts/${id}/disable`,
    });
    expect(disabled.json().enabled).toBe(false);

    const enabled = await server.app.inject({
      method: 'POST',
      url: `/api/v1/accounts/${id}/enable`,
    });
    expect(enabled.json().enabled).toBe(true);
  });

  it('deletes an account and its profile directory', async () => {
    const created = await createAccount('Alpha');
    const id = created.json().id;

    const response = await server.app.inject({ method: 'DELETE', url: `/api/v1/accounts/${id}` });
    expect(response.statusCode).toBe(204);
    expect(existsSync(join(server.directory, 'browser-profiles', 'alpha'))).toBe(false);

    const after = await server.app.inject({ method: 'GET', url: `/api/v1/accounts/${id}` });
    expect(after.statusCode).toBe(404);
  });

  it('imports accounts and reports what it skipped', async () => {
    await createAccount('Existing');

    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts/import',
      payload: {
        accounts: [{ name: 'Imported One' }, { name: 'Imported Two' }, { name: 'Existing' }],
      },
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ created: 2, updated: 0 });
    expect(response.json().skipped).toHaveLength(1);
  });

  it('updates existing accounts when the import asks to upsert', async () => {
    await createAccount('Existing');

    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts/import',
      payload: {
        upsert: true,
        accounts: [{ name: 'Existing', displayName: 'Renamed by import' }],
      },
    });

    expect(response.json()).toMatchObject({ created: 0, updated: 1 });
  });

  it('exports every account as a downloadable document', async () => {
    await createAccount('Alpha');

    const response = await server.app.inject({ method: 'GET', url: '/api/v1/accounts/export' });

    expect(response.statusCode).toBe(200);
    expect(response.headers['content-disposition']).toContain('accounts.json');
    expect(response.json().accounts).toHaveLength(1);
  });

  it('answers a typed 404 for an unknown route', async () => {
    const response = await server.app.inject({ method: 'GET', url: '/api/v1/nope' });

    expect(response.statusCode).toBe(404);
    expect(response.json().error.code).toBe(ERROR_CODES.NOT_FOUND);
  });

  it('echoes a request id on every response', async () => {
    const response = await server.app.inject({ method: 'GET', url: '/api/v1/health' });
    expect(response.headers['x-request-id']).toBeTruthy();
  });
});
