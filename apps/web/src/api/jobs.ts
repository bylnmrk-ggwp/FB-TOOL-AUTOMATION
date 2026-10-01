import {
  JobSchema,
  paginatedSchema,
  QueueStatsSchema,
  type CreateJobBatchInput,
  type Job,
  type ListJobsQuery,
  type Paginated,
  type QueueStats,
  type ReactionType,
} from '@fb/shared';
import { z } from 'zod';
import { apiRequest } from './client';

const JobPageSchema = paginatedSchema(JobSchema);
const JobsSchema = z.object({ jobs: z.array(JobSchema) });

export const listJobs = (
  query: Partial<ListJobsQuery>,
  signal?: AbortSignal,
): Promise<Paginated<Job>> =>
  apiRequest('/jobs', JobPageSchema, {
    signal,
    query: {
      limit: query.limit ?? 50,
      offset: query.offset ?? 0,
      status: query.status === undefined ? undefined : [...query.status],
      accountId: query.accountId,
      type: query.type,
    },
  });

export const getJob = (id: string, signal?: AbortSignal): Promise<Job> =>
  apiRequest(`/jobs/${id}`, JobSchema, { signal });

export const createJobBatch = (input: CreateJobBatchInput): Promise<{ jobs: Job[] }> =>
  apiRequest('/jobs/batch', JobsSchema, { method: 'POST', body: input });

export interface ShareToGroupsInput {
  accountIds: string[];
  postUrl: string;
  groups: Array<{ name: string; url: string | null }>;
  comments: string[];
  reaction: ReactionType | null;
  shareToTimeline: boolean;
  skipDone: boolean;
  priority?: number;
}

export const shareToGroups = (input: ShareToGroupsInput): Promise<{ jobs: Job[] }> =>
  apiRequest('/jobs/share-to-groups', JobsSchema, { method: 'POST', body: input });

export interface CommentPostInput {
  accountIds: string[];
  postUrl: string;
  comments: string[];
  then: 'none' | 'react' | 'timeline' | 'story';
  reaction: ReactionType | null;
  skipDone: boolean;
  priority?: number;
  scheduledFor?: string;
}

export const commentPost = (input: CommentPostInput): Promise<{ jobs: Job[] }> =>
  apiRequest('/jobs/comment-post', JobsSchema, { method: 'POST', body: input });

export interface JoinGroupsInput {
  accountIds: string[];
  groupUrls: string[];
  skipDone: boolean;
  priority?: number;
}

export const joinGroups = (input: JoinGroupsInput): Promise<{ jobs: Job[] }> =>
  apiRequest('/jobs/join-groups', JobsSchema, { method: 'POST', body: input });

export const cancelJob = (id: string): Promise<Job> =>
  apiRequest(`/jobs/${id}/cancel`, JobSchema, { method: 'POST' });

export const cancelAllJobs = (): Promise<{ cancelled: number }> =>
  apiRequest('/jobs/cancel-all', z.object({ cancelled: z.number().int().min(0) }), {
    method: 'POST',
  });

export const retryJob = (id: string): Promise<Job> =>
  apiRequest(`/jobs/${id}/retry`, JobSchema, { method: 'POST' });

export const getQueueStats = (signal?: AbortSignal): Promise<QueueStats> =>
  apiRequest('/jobs/stats', QueueStatsSchema, { signal });
