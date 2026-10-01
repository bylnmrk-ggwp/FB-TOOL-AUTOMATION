import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { Job, JobStatus } from '@fb/shared';
import { createTestServer, type TestServer } from '../helpers/server';

const POST_URL = 'https://www.facebook.com/example/posts/42';

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
  throw new Error(`Job ${jobId} never reached ${statuses.join(' or ')}`);
};

describe('Comment on a post', () => {
  let server: TestServer;
  let accountIds: string[];

  const createAccount = async (name: string): Promise<string> => {
    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/accounts',
      payload: { name },
    });
    return response.json().id;
  };

  const commentPost = async (payload: Record<string, unknown>): Promise<Job[]> => {
    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/jobs/comment-post',
      payload: { accountIds, postUrl: POST_URL, ...payload },
    });
    expect(response.statusCode, response.body).toBe(201);
    return (response.json() as { jobs: Job[] }).jobs;
  };

  beforeEach(async () => {
    // The queue stays stopped so the jobs can be read back exactly as created.
    server = await createTestServer({ autoStartQueue: false });
    accountIds = [
      await createAccount('Alpha'),
      await createAccount('Bravo'),
      await createAccount('Charlie'),
    ];
  });

  afterEach(async () => {
    await server.dispose();
  });

  it('gives line n to account n and repeats the lines when accounts outnumber them', async () => {
    const jobs = await commentPost({ comments: ['first', 'second'] });

    // Jobs come back in no particular order; what matters is which account got which line.
    expect(jobs.map((job) => job.type)).toEqual(['comment', 'comment', 'comment']);
    const textFor = new Map(
      jobs.map((job) => [job.accountId, job.payload.type === 'comment' ? job.payload.text : null]),
    );
    expect(accountIds.map((id) => textFor.get(id))).toEqual(['first', 'second', 'first']);
  });

  it('adds a reaction job per account when asked to react', async () => {
    const jobs = await commentPost({ comments: ['hello'], then: 'react', reaction: 'love' });

    expect(jobs).toHaveLength(6);
    const reactions = jobs.filter((job) => job.payload.type === 'react_to_post');
    expect(reactions.map((job) => job.accountId).sort()).toEqual([...accountIds].sort());
    expect(
      reactions.every(
        (job) => job.payload.type === 'react_to_post' && job.payload.reaction === 'love',
      ),
    ).toBe(true);
  });

  it('folds a story share and the comment into one share job', async () => {
    const jobs = await commentPost({ comments: ['one', 'two', 'three'], then: 'story' });

    expect(jobs.map((job) => job.type)).toEqual(['share_post', 'share_post', 'share_post']);
    const second = jobs.find((job) => job.accountId === accountIds[1])?.payload;
    expect(second?.type === 'share_post' ? second.targets : null).toEqual(['story']);
    expect(second?.type === 'share_post' ? second.comments : null).toEqual(['two']);
  });

  it('skips what an account already did to the post, unless told not to', async () => {
    await server.dispose();
    server = await createTestServer();
    accountIds = [await createAccount('Delta')];

    const first = await commentPost({ comments: ['again?'], then: 'react' });
    expect(first).toHaveLength(2);
    for (const job of first) await waitForStatus(server, job.id, ['completed']);

    expect(await commentPost({ comments: ['again?'], then: 'react' })).toHaveLength(0);
    expect(
      await commentPost({ comments: ['again?'], then: 'react', skipDone: false }),
    ).toHaveLength(2);
  });
});
