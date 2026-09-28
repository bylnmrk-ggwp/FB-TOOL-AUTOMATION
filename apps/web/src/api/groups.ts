import {
  GroupSchema,
  GroupSummarySchema,
  JobSchema,
  OperatorRequestSchema,
  paginatedSchema,
  type AnswerOperatorRequestInput,
  type Group,
  type GroupSummary,
  type Job,
  type ListGroupsQuery,
  type OperatorRequest,
  type Paginated,
} from '@fb/shared';
import { z } from 'zod';
import { apiRequest } from './client';

const GroupPageSchema = paginatedSchema(GroupSchema);

export const listGroups = (
  query: Partial<ListGroupsQuery>,
  signal?: AbortSignal,
): Promise<Paginated<Group>> =>
  apiRequest('/groups', GroupPageSchema, {
    signal,
    query: {
      limit: query.limit ?? 200,
      offset: query.offset ?? 0,
      accountId: query.accountId,
      search: query.search,
    },
  });

export const groupSummaries = (signal?: AbortSignal): Promise<GroupSummary[]> =>
  apiRequest('/groups/summary', z.object({ groups: z.array(GroupSummarySchema) }), { signal }).then(
    (result) => result.groups,
  );

export const fetchGroups = (accountIds: string[]): Promise<Job[]> =>
  apiRequest('/groups/fetch', z.object({ jobs: z.array(JobSchema) }), {
    method: 'POST',
    body: { accountIds },
  }).then((result) => result.jobs);

export const listOperatorRequests = (signal?: AbortSignal): Promise<OperatorRequest[]> =>
  apiRequest('/input', z.object({ requests: z.array(OperatorRequestSchema) }), { signal }).then(
    (result) => result.requests,
  );

export const answerOperatorRequest = (input: AnswerOperatorRequestInput): Promise<null> =>
  apiRequest('/input', z.null(), { method: 'POST', body: input });
