import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createRepositories } from '@fb/database';
import type { Repositories } from '@fb/application';
import { createId, DEFAULT_SETTINGS, type AutomationAction } from '@fb/shared';
import { createTestDatabase, type TestDatabase } from '../helpers/database';

const POST: AutomationAction = {
  type: 'create_post',
  text: 'hello',
  media: [],
  audience: 'friends',
};

describe('SQLite repositories', () => {
  let database: TestDatabase;
  let repositories: Repositories;

  beforeEach(() => {
    database = createTestDatabase();
    repositories = createRepositories(database, 'test-worker');
  });

  afterEach(() => {
    database.dispose();
  });

  const newAccount = async (name: string) => {
    const accountId = createId('acc');
    const profileId = createId('prf');
    const account = await repositories.accounts.create({
      id: accountId,
      name,
      displayName: name,
      profileId,
      status: 'offline',
      enabled: true,
    });
    await repositories.profiles.create({
      id: profileId,
      accountId,
      slug: name,
      directory: name,
      channel: 'chromium',
    });
    return account;
  };

  const profileIdOf = async (accountId: string): Promise<string> => {
    const profile = await repositories.profiles.findByAccountId(accountId);
    if (profile === null) throw new Error(`No profile for ${accountId}`);
    return profile.id;
  };

  const addJob = async (accountId: string, priority = 0, runAfter: string | null = null) =>
    repositories.jobs.create({
      id: createId('job'),
      accountId,
      type: 'create_post',
      payload: POST,
      priority,
      maxRetries: 2,
      status: 'pending',
      runAfter,
    });

  it('creates and reads an account back', async () => {
    const created = await newAccount('alpha');

    expect(created.status).toBe('offline');
    expect(created.enabled).toBe(true);
    expect((await repositories.accounts.findById(created.id))?.name).toBe('alpha');
    expect((await repositories.accounts.findByName('alpha'))?.id).toBe(created.id);
  });

  it('filters and paginates the account list', async () => {
    await newAccount('alpha');
    await newAccount('beta');
    await newAccount('gamma');

    const page = await repositories.accounts.list({ limit: 2, offset: 0 });
    expect(page.total).toBe(3);
    expect(page.items).toHaveLength(2);

    const searched = await repositories.accounts.list({ limit: 10, offset: 0, search: 'bet' });
    expect(searched.items.map((account) => account.name)).toEqual(['beta']);
  });

  it('rejects a duplicate account name', async () => {
    await newAccount('alpha');
    await expect(newAccount('alpha')).rejects.toThrow();
  });

  it('updates status and counts by status', async () => {
    const account = await newAccount('alpha');
    await repositories.accounts.update(account.id, { status: 'online' });

    const counts = await repositories.accounts.countByStatus();
    expect(counts.online).toBe(1);
    expect(counts.offline).toBe(0);
  });

  it('returns mid-session accounts to offline on restart', async () => {
    const first = await newAccount('alpha');
    const second = await newAccount('beta');
    await repositories.accounts.update(first.id, { status: 'online' });
    await repositories.accounts.update(second.id, { status: 'busy' });

    expect(await repositories.accounts.resetRuntimeStatuses()).toBe(2);
    expect((await repositories.accounts.countByStatus()).offline).toBe(2);
  });

  it('grants a profile lock once and refuses the second holder', async () => {
    const account = await newAccount('alpha');
    const profileId = await profileIdOf(account.id);
    const now = new Date();

    expect(await repositories.profiles.tryAcquireLock(profileId, 'worker-a', now, 60_000)).toBe(
      true,
    );
    expect(await repositories.profiles.tryAcquireLock(profileId, 'worker-b', now, 60_000)).toBe(
      false,
    );
  });

  it('lets a new holder take an expired lock', async () => {
    const account = await newAccount('alpha');
    const profileId = await profileIdOf(account.id);

    const acquiredAt = new Date('2026-01-01T00:00:00.000Z');
    await repositories.profiles.tryAcquireLock(profileId, 'worker-a', acquiredAt, 60_000);

    const muchLater = new Date(acquiredAt.getTime() + 120_000);
    expect(
      await repositories.profiles.tryAcquireLock(profileId, 'worker-b', muchLater, 60_000),
    ).toBe(true);
  });

  it('releases every lock a worker holds', async () => {
    const now = new Date();
    for (const name of ['alpha', 'beta']) {
      const account = await newAccount(name);
      const profileId = await profileIdOf(account.id);
      await repositories.profiles.tryAcquireLock(profileId, 'worker-a', now, 60_000);
    }

    expect(await repositories.profiles.releaseLocksOwnedBy('worker-a')).toBe(2);
    expect(await repositories.profiles.listLocked()).toHaveLength(0);
  });

  it('stores a job payload and reads it back as a typed action', async () => {
    const account = await newAccount('alpha');
    const job = await addJob(account.id);

    expect(job.payload.type).toBe('create_post');
    if (job.payload.type === 'create_post') expect(job.payload.text).toBe('hello');
    expect((await repositories.jobs.stats()).pending).toBe(1);
  });

  it('claims one job per account and skips busy accounts', async () => {
    const alpha = await newAccount('alpha');
    const beta = await newAccount('beta');
    await addJob(alpha.id);
    await addJob(alpha.id);
    await addJob(beta.id);

    const claimed = await repositories.jobs.claimDueJobs({
      busyAccountIds: [],
      now: new Date(),
      limit: 10,
    });

    expect(claimed).toHaveLength(2);
    expect(new Set(claimed.map((job) => job.accountId)).size).toBe(2);
    expect(claimed.every((job) => job.status === 'queued')).toBe(true);

    const second = await repositories.jobs.claimDueJobs({
      busyAccountIds: [alpha.id, beta.id],
      now: new Date(),
      limit: 10,
    });
    expect(second).toHaveLength(0);
  });

  it('does not claim a job scheduled for later', async () => {
    const account = await newAccount('alpha');
    await addJob(account.id, 0, new Date(Date.now() + 60_000).toISOString());

    const claimed = await repositories.jobs.claimDueJobs({
      busyAccountIds: [],
      now: new Date(),
      limit: 10,
    });
    expect(claimed).toHaveLength(0);
  });

  it('claims the highest priority job first', async () => {
    const account = await newAccount('alpha');
    await addJob(account.id, 0);
    const urgent = await addJob(account.id, 50);

    const claimed = await repositories.jobs.claimDueJobs({
      busyAccountIds: [],
      now: new Date(),
      limit: 1,
    });
    expect(claimed[0]?.id).toBe(urgent.id);
  });

  it('appends and filters logs', async () => {
    const account = await newAccount('alpha');

    await repositories.logs.append({
      id: createId('log'),
      level: 'info',
      message: 'browser started',
      event: 'browser.started',
      accountId: account.id,
      jobId: null,
      sessionId: null,
      requestId: null,
      context: { headless: false },
    });
    await repositories.logs.append({
      id: createId('log'),
      level: 'error',
      message: 'launch failed',
      event: 'browser.error',
      accountId: account.id,
      jobId: null,
      sessionId: null,
      requestId: null,
      context: null,
    });

    const errors = await repositories.logs.list({ limit: 10, offset: 0, level: ['error'] });
    expect(errors.total).toBe(1);
    expect(errors.items[0]?.message).toBe('launch failed');

    const searched = await repositories.logs.list({ limit: 10, offset: 0, search: 'browser' });
    expect(searched.total).toBe(1);
  });

  it('merges stored settings over the defaults', async () => {
    expect(await repositories.settings.read()).toEqual(DEFAULT_SETTINGS);

    const updated = await repositories.settings.write({ globalConcurrency: 5 });
    expect(updated.globalConcurrency).toBe(5);
    expect(updated.headless).toBe(DEFAULT_SETTINGS.headless);
    expect((await repositories.settings.read()).globalConcurrency).toBe(5);
  });
});
