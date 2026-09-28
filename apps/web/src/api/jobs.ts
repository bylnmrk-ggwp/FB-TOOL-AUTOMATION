import {
  JobSchema,
  paginatedSchema,
  QueueStatsSchema,
  type CreateJobBatchInput,
  type Job,
  type ListJobsQuery,
  type Paginated,
  type QueueStats,
} from '@fb/shared';
import { z } from 'zod';
import { apiRequest } from './client';

const JobPageSchema = paginatedSchema(JobSchema);

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
  apiRequest('/jobs/batch', z.object({ jobs: z.array(JobSchema) }), {
    method: 'POST',
    body: input,
  });

export const cancelJob = (id: string): Promise<Job> =>
  apiRequest(`/jobs/${id}/cancel`, JobSchema, { method: 'POST' });

export const retryJob = (id: string): Promise<Job> =>
  apiRequest(`/jobs/${id}/retry`, JobSchema, { method: 'POST' });

export const getQueueStats = (signal?: AbortSignal): Promise<QueueStats> =>
  apiRequest('/jobs/stats', QueueStatsSchema, { signal });
