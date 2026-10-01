import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ERROR_CODES, type Job, type JobStatus } from '@fb/shared';
import {
  AutomationBlockedError,
  AutomationTimeoutError,
  LoginFailedError,
  NotLoggedInError,
} from '@fb/shared';
import { FakeGateway } from '../helpers/fake-gateway';
import { createTestServer, type TestServer } from '../helpers/server';

const POST = { type: 'create_post', text: 'hello', media: [], audience: 'friends' } as const;
const WATCH = { type: 'watch_live', url: 'https://www.facebook.com/live/1', minutes: 1 } as const;

/** Polls the API until the job reaches one of the given states. */
const waitForStatus = async (
  server: TestServer,
  jobId: string,
  statuses: readonly JobStatus[],
  timeoutMs = 8_000,
): Promise<Job> => {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const response = await server.app.inject({ method: 'GET', url: `/api/v1/jobs/${jobId}` });
    const job = response.json() as Job;
    if (statuses.includes(job.status)) return job;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }

  const last = await server.app.inject({ method: 'GET', url: `/api/v1/jobs/${jobId}` });
  throw new Error(
    `Job ${jobId} never reached ${statuses.join(' or ')}; it is ${last.json().status}`,
  );
};

/** Hanging jobs are cancelled before the server goes, or dispose waits on them. */
const cancelAll = async (server: TestServer, jobs: readonly Job[]): Promise<void> => {
  for (const job of jobs) {
    await server.app.inject({ method: 'POST', url: `/api/v1/jobs/${job.id}/cancel` });
  }
  for (const job of jobs) await waitForStatus(server, job.id, ['cancelled', 'completed', 'failed']);
};

describe('Queue', () => {
  let server: TestServer;
  let accountId: string;

  const createAccount = async (name: string): Promise<string> => {
    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name },
    });
    return response.json().id;
  };

  const createJob = async (payload: Record<string, unknown>) =>
    server.app.inject({ method: 'POST', url: '/api/v1/jobs', payload });

  beforeEach(async () => {
    server = await createTestServer();
    accountId = await createAccount('Alpha');
  });

  afterEach(async () => {
    await server.dispose();
  });

  it('runs a job through to completion', async () => {
    const created = await createJob({ accountId, action: POST });
    expect(created.statusCode).toBe(201);

    const job = await waitForStatus(server, created.json().id, ['completed']);

    expect(job.progress).toBe(100);
    expect(job.result?.resourceUrl).toContain('example.invalid');
    expect(job.finishedAt).not.toBeNull();
    expect(server.gateway.executions).toHaveLength(1);
  });

  it('starts a browser for a job, then closes it when the job finishes', async () => {
    const created = await createJob({ accountId, action: POST });
    await waitForStatus(server, created.json().id, ['completed']);

    // The queue opened a browser for the job...
    expect(server.browser.startCount).toBeGreaterThan(0);
    // ...and closed the one it opened, so a batch cannot leave a browser per
    // account running until the machine is out of memory.
    expect(server.browser.isRunning(accountId)).toBe(false);
    // A post needs no video, so the browser was asked for lite.
    expect(server.browser.starts.at(-1)?.needsMedia).toBeUndefined();
  });

  it('closes every browser on Stop everything, viewers included', async () => {
    server.gateway.thenHang();
    const created = await createJob({ accountId, action: WATCH });
    await server.gateway.waitForStarts(1);
    expect(server.browser.isRunning(accountId)).toBe(true);

    const response = await server.app.inject({ method: 'POST', url: '/api/v1/jobs/cancel-all' });
    expect(response.statusCode).toBe(200);
    await waitForStatus(server, created.json().id, ['cancelled']);
    expect(server.browser.isRunning(accountId)).toBe(false);
  });

  it('closes the viewer and moves on when the account cannot get past the login screen', async () => {
    server.gateway.alwaysFail(new NotLoggedInError(accountId));
    const created = await createJob({ accountId, action: WATCH, maxRetries: 0 });
    await waitForStatus(server, created.json().id, ['failed']);

    expect(server.browser.isRunning(accountId)).toBe(false);
  });

  it('leaves the browser open after a watch-live job, so the viewer stays', async () => {
    const created = await createJob({ accountId, action: WATCH });
    await waitForStatus(server, created.json().id, ['completed']);

    expect(server.browser.startCount).toBeGreaterThan(0);
    expect(server.browser.isRunning(accountId)).toBe(true);
    // ...and it was opened with media allowed, or the video could never play.
    expect(server.browser.starts.at(-1)?.needsMedia).toBe(true);
  });

  it('reports progress and the finished state over the event bus', async () => {
    const created = await createJob({ accountId, action: POST });
    await waitForStatus(server, created.json().id, ['completed']);

    const types = server.events.map((event) => event.type);
    expect(types).toContain('job.created');
    expect(types).toContain('job.started');
    expect(types).toContain('job.progress');
    expect(types).toContain('job.completed');
  });

  it('refuses to create a job for a disabled account', async () => {
    await server.app.inject({ method: 'POST', url: `/api/v1/accounts/${accountId}/disable` });
    const response = await createJob({ accountId, action: POST });

    expect(response.statusCode).toBe(409);
    expect(response.json().error.code).toBe(ERROR_CODES.ACCOUNT_DISABLED);
  });

  it('refuses to create a job for an account that does not exist', async () => {
    const response = await createJob({ accountId: 'acc_missing', action: POST });

    expect(response.statusCode).toBe(404);
    expect(response.json().error.code).toBe(ERROR_CODES.ACCOUNT_NOT_FOUND);
  });

  it('creates one job per account from a batch', async () => {
    const second = await createAccount('Beta');

    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs/batch',
      payload: { accountIds: [accountId, second], action: POST },
    });

    expect(response.statusCode).toBe(201);
    expect(response.json().jobs).toHaveLength(2);
  });

  it('writes nothing when one account in a batch is unusable', async () => {
    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs/batch',
      payload: { accountIds: [accountId, 'acc_missing'], action: POST },
    });

    expect(response.statusCode).toBe(404);
    expect((await server.container.repositories.jobs.stats()).pending).toBe(0);
  });

  it('holds a scheduled job until it is due', async () => {
    const created = await createJob({
      accountId,
      action: POST,
      scheduledFor: new Date(Date.now() + 60_000).toISOString(),
    });

    await new Promise((resolve) => setTimeout(resolve, 300));

    const job = await server.app.inject({
      method: 'GET',
      url: `/api/v1/jobs/${created.json().id}`,
    });
    expect(job.json().status).toBe('pending');
    expect(server.gateway.executions).toHaveLength(0);
  });

  it('cancels a job that has not started', async () => {
    const created = await createJob({
      accountId,
      action: POST,
      scheduledFor: new Date(Date.now() + 60_000).toISOString(),
    });

    const response = await server.app.inject({
      method: 'POST',
      url: `/api/v1/jobs/${created.json().id}/cancel`,
    });

    expect(response.statusCode).toBe(200);
    expect(response.json().status).toBe('cancelled');
  });

  it('refuses to cancel a job that already finished', async () => {
    const created = await createJob({ accountId, action: POST });
    await waitForStatus(server, created.json().id, ['completed']);

    const response = await server.app.inject({
      method: 'POST',
      url: `/api/v1/jobs/${created.json().id}/cancel`,
    });

    expect(response.statusCode).toBe(409);
    expect(response.json().error.code).toBe(ERROR_CODES.JOB_NOT_CANCELLABLE);
  });

  it('retries a failed job on request and clears the previous error', async () => {
    server.gateway.alwaysFail(new AutomationBlockedError('not this time'));

    const created = await createJob({ accountId, action: POST, maxRetries: 0 });
    const failed = await waitForStatus(server, created.json().id, ['failed']);
    expect(failed.lastError?.code).toBe(ERROR_CODES.AUTOMATION_BLOCKED);

    server.gateway.alwaysSucceed();
    const retried = await server.app.inject({
      method: 'POST',
      url: `/api/v1/jobs/${created.json().id}/retry`,
    });

    expect(retried.statusCode).toBe(200);
    expect(retried.json().lastError).toBeNull();
    await waitForStatus(server, created.json().id, ['completed']);
  });

  it('refuses to retry a job that succeeded', async () => {
    const created = await createJob({ accountId, action: POST });
    await waitForStatus(server, created.json().id, ['completed']);

    const response = await server.app.inject({
      method: 'POST',
      url: `/api/v1/jobs/${created.json().id}/retry`,
    });

    expect(response.statusCode).toBe(409);
    expect(response.json().error.code).toBe(ERROR_CODES.JOB_NOT_RETRYABLE);
  });

  it('leaves the login verdict alone when the failure says nothing about the account', async () => {
    // A browser that would not launch or a page that timed out is the machine
    // failing, not Facebook refusing: the roster must not call it logged out.
    server.gateway.alwaysFail(new AutomationTimeoutError('navigate to facebook', 30_000));

    const created = await createJob({ accountId, action: { type: 'login' }, maxRetries: 0 });
    await waitForStatus(server, created.json().id, ['failed']);

    const account = await server.app.inject({
      method: 'GET',
      url: `/api/v1/accounts/${accountId}`,
    });
    expect(account.statusCode).toBe(200);
    expect(account.json().loginStatus).toBe('unknown');
    expect(account.json().lastLoginCheckAt).toBeNull();
  });

  it('marks the account logged out when any job finds the session gone', async () => {
    server.gateway.alwaysFail(new NotLoggedInError(accountId));

    const created = await createJob({ accountId, action: POST, maxRetries: 0 });
    await waitForStatus(server, created.json().id, ['failed']);

    const account = await server.app.inject({
      method: 'GET',
      url: `/api/v1/accounts/${accountId}`,
    });
    expect(account.statusCode).toBe(200);
    expect(account.json().loginStatus).toBe('logged_out');
  });

  it('records logged out when Facebook itself refused the login', async () => {
    server.gateway.alwaysFail(new LoginFailedError('wrong password'));

    const created = await createJob({ accountId, action: { type: 'login' }, maxRetries: 0 });
    await waitForStatus(server, created.json().id, ['failed']);

    const account = await server.app.inject({
      method: 'GET',
      url: `/api/v1/accounts/${accountId}`,
    });
    expect(account.statusCode).toBe(200);
    expect(account.json().loginStatus).toBe('logged_out');
    expect(account.json().loginReason).toBe('Login failed: wrong password');
  });

  it('does not retry an error that says it cannot be retried', async () => {
    server.gateway.alwaysFail(new AutomationBlockedError('the action was refused'));

    const created = await createJob({ accountId, action: POST, maxRetries: 3 });
    const job = await waitForStatus(server, created.json().id, ['failed']);

    expect(job.retryCount).toBe(0);
    expect(server.gateway.executions).toHaveLength(1);
  });

  it('exposes queue statistics', async () => {
    const created = await createJob({ accountId, action: POST });
    await waitForStatus(server, created.json().id, ['completed']);

    const response = await server.app.inject({ method: 'GET', url: '/api/v1/jobs/stats' });
    expect(response.json().completed).toBe(1);
  });

  it('filters the job list by status and account', async () => {
    const created = await createJob({ accountId, action: POST });
    await waitForStatus(server, created.json().id, ['completed']);

    const byStatus = await server.app.inject({
      method: 'GET',
      url: '/api/v1/jobs?status=completed',
    });
    expect(byStatus.json().total).toBe(1);

    const byAccount = await server.app.inject({
      method: 'GET',
      url: `/api/v1/jobs?accountId=${accountId}`,
    });
    expect(byAccount.json().total).toBe(1);
  });
});

describe('Queue concurrency', () => {
  let server: TestServer;

  afterEach(async () => {
    await server.dispose();
  });

  const createAccount = async (name: string): Promise<string> => {
    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name },
    });
    return response.json().id;
  };

  it('runs one job at a time per account', async () => {
    const gateway = new FakeGateway().thenDelay(250).thenDelay(10);
    server = await createTestServer({ gateway, concurrency: 4 });
    const accountId = await createAccount('Alpha');

    const first = await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs',
      payload: { accountId, action: POST },
    });
    const second = await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs',
      payload: { accountId, action: POST },
    });

    await waitForStatus(server, first.json().id, ['completed']);
    await waitForStatus(server, second.json().id, ['completed']);

    const [a, b] = gateway.executions;
    expect(a).toBeDefined();
    expect(b).toBeDefined();
    // The second execution cannot have begun before the first one ended.
    expect(b!.startedAt).toBeGreaterThanOrEqual(a!.finishedAt);
  });

  it('runs different accounts at the same time', async () => {
    const gateway = new FakeGateway().thenDelay(200).thenDelay(200);
    server = await createTestServer({ gateway, concurrency: 4 });

    const alpha = await createAccount('Alpha');
    const beta = await createAccount('Beta');

    await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs/batch',
      payload: { accountIds: [alpha, beta], action: POST },
    });

    await gateway.waitForStarts(2);
    expect(gateway.executions.length).toBeLessThanOrEqual(2);
  });

  it('never exceeds the global concurrency limit', async () => {
    const gateway = new FakeGateway();
    server = await createTestServer({ gateway, concurrency: 1 });

    const alpha = await createAccount('Alpha');
    const beta = await createAccount('Beta');

    await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs/batch',
      payload: { accountIds: [alpha, beta], action: POST },
    });

    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(server.container.queue.capacity().limit).toBe(1);
    expect(server.container.queue.capacity().busy).toBeLessThanOrEqual(1);
  });

  it('starts every watch-live job at once, in a lane outside the global limit', async () => {
    const gateway = new FakeGateway().thenHang().thenHang().thenHang();
    server = await createTestServer({ gateway, concurrency: 1 });
    const viewers = [
      await createAccount('Alpha'),
      await createAccount('Beta'),
      await createAccount('Gamma'),
    ];

    const watching = await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs/batch',
      payload: { accountIds: viewers, action: WATCH },
    });
    await gateway.waitForStarts(3);
    expect(server.container.queue.capacity().busy).toBe(3);

    // The ordinary lane is untouched: a post still starts beside three viewers.
    const poster = await createAccount('Delta');
    await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs/batch',
      payload: { accountIds: [poster], action: POST },
    });
    await gateway.waitForStarts(4);

    await cancelAll(server, (watching.json() as { jobs: Job[] }).jobs);
  });

  it('caps the live lane when a limit is set', async () => {
    const gateway = new FakeGateway().thenHang().thenHang().thenHang();
    server = await createTestServer({ gateway, concurrency: 1 });
    await server.app.inject({
      method: 'PATCH',
      url: '/api/v1/settings',
      payload: { liveViewersAtOnce: 2 },
    });
    const viewers = [
      await createAccount('Alpha'),
      await createAccount('Beta'),
      await createAccount('Gamma'),
    ];

    const watching = await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs/batch',
      payload: { accountIds: viewers, action: WATCH },
    });
    await gateway.waitForStarts(2);
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(server.container.queue.runningJobs()).toHaveLength(2);

    await cancelAll(server, (watching.json() as { jobs: Job[] }).jobs);
  });
});

describe('Queue cancellation and recovery', () => {
  let server: TestServer;

  afterEach(async () => {
    if (server !== undefined) await server.dispose();
  });

  it('aborts a running job when it is cancelled', async () => {
    const gateway = new FakeGateway().thenHang();
    server = await createTestServer({ gateway });

    const account = await server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name: 'Alpha' },
    });
    const created = await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs',
      payload: { accountId: account.json().id, action: POST },
    });

    await gateway.waitForStarts(1);
    await waitForStatus(server, created.json().id, ['running']);

    const cancelled = await server.app.inject({
      method: 'POST',
      url: `/api/v1/jobs/${created.json().id}/cancel`,
    });
    expect(cancelled.statusCode).toBe(200);

    const job = await waitForStatus(server, created.json().id, ['cancelled']);
    expect(job.finishedAt).not.toBeNull();
  });

  it('brings a queued job back after a restart', async () => {
    // The queue stays stopped so the job is claimed by nothing and left
    // exactly as a killed process would leave it.
    const first = await createTestServer({ autoStartQueue: false });
    const account = await first.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name: 'Alpha' },
    });
    const created = await first.app.inject({
      method: 'POST',
      url: '/api/v1/jobs',
      payload: { accountId: account.json().id, action: POST },
    });
    const jobId = created.json().id;

    await first.container.repositories.jobs.update(jobId, {
      status: 'queued',
      queuedAt: new Date().toISOString(),
    });
    const directory = first.directory;
    await first.dispose(true);

    server = await createTestServer({ directory });
    const recovered = await waitForStatus(server, jobId, ['completed']);
    expect(recovered.status).toBe('completed');
  });

  it('does not repeat a job that was interrupted mid-run', async () => {
    const first = await createTestServer({ autoStartQueue: false });
    const account = await first.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name: 'Alpha' },
    });
    const created = await first.app.inject({
      method: 'POST',
      url: '/api/v1/jobs',
      payload: { accountId: account.json().id, action: POST },
    });
    const jobId = created.json().id;

    await first.container.repositories.jobs.update(jobId, {
      status: 'running',
      startedAt: new Date().toISOString(),
    });
    const directory = first.directory;
    await first.dispose(true);

    const gateway = new FakeGateway();
    server = await createTestServer({ directory, gateway });

    const job = await waitForStatus(server, jobId, ['failed']);
    expect(job.lastError?.message).toContain('may have partly completed');
    // Crucially, it was not run again behind the operator's back.
    expect(gateway.executions).toHaveLength(0);
  });
});
