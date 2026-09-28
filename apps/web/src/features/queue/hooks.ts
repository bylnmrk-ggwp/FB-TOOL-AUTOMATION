import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import type { CreateJobBatchInput, Job, ListJobsQuery, Paginated, QueueStats } from '@fb/shared';
import {
  cancelAllJobs,
  cancelJob,
  createJobBatch,
  getQueueStats,
  joinGroups,
  listJobs,
  retryJob,
  shareToGroups,
  type JoinGroupsInput,
  type ShareToGroupsInput,
} from '../../api/jobs';

export const jobKeys = {
  all: ['jobs'] as const,
  list: (query: Partial<ListJobsQuery>) => ['jobs', 'list', query] as const,
  stats: ['queue-stats'] as const,
};

export const useJobs = (query: Partial<ListJobsQuery> = {}): UseQueryResult<Paginated<Job>> =>
  useQuery({
    queryKey: jobKeys.list(query),
    queryFn: ({ signal }) => listJobs(query, signal),
    placeholderData: (previous) => previous,
  });

export const useQueueStats = (): UseQueryResult<QueueStats> =>
  useQuery({
    queryKey: jobKeys.stats,
    queryFn: ({ signal }) => getQueueStats(signal),
  });

const useJobMutation = <TInput, TResult>(
  mutationFn: (input: TInput) => Promise<TResult>,
): UseMutationResult<TResult, Error, TInput> => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: jobKeys.all });
      void queryClient.invalidateQueries({ queryKey: jobKeys.stats });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
};

export const useCancelJob = (): UseMutationResult<Job, Error, string> => useJobMutation(cancelJob);

export const useCancelAllJobs = (): UseMutationResult<{ cancelled: number }, Error, void> =>
  useJobMutation(() => cancelAllJobs());

export const useRetryJob = (): UseMutationResult<Job, Error, string> => useJobMutation(retryJob);

export const useCreateJobs = (): UseMutationResult<{ jobs: Job[] }, Error, CreateJobBatchInput> =>
  useJobMutation(createJobBatch);

export const useShareToGroups = (): UseMutationResult<{ jobs: Job[] }, Error, ShareToGroupsInput> =>
  useJobMutation(shareToGroups);

export const useJoinGroups = (): UseMutationResult<{ jobs: Job[] }, Error, JoinGroupsInput> =>
  useJobMutation(joinGroups);
