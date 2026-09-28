import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import type {
  AnswerOperatorRequestInput,
  Group,
  GroupSummary,
  Job,
  ListGroupsQuery,
  OperatorRequest,
  Paginated,
} from '@fb/shared';
import {
  answerOperatorRequest,
  fetchGroups,
  groupSummaries,
  listGroups,
  listOperatorRequests,
} from '../../api/groups';

export const useGroups = (query: Partial<ListGroupsQuery> = {}): UseQueryResult<Paginated<Group>> =>
  useQuery({
    queryKey: ['groups', 'list', query],
    queryFn: ({ signal }) => listGroups(query, signal),
    placeholderData: (previous) => previous,
  });

export const useGroupSummaries = (): UseQueryResult<GroupSummary[]> =>
  useQuery({
    queryKey: ['groups', 'summary'],
    queryFn: ({ signal }) => groupSummaries(signal),
  });

export const useFetchGroups = (): UseMutationResult<Job[], Error, string[]> => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fetchGroups,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
};

export const useOperatorRequests = (): UseQueryResult<OperatorRequest[]> =>
  useQuery({
    queryKey: ['operator-requests'],
    queryFn: ({ signal }) => listOperatorRequests(signal),
    // The socket refreshes this the moment a job asks; polling is the fallback.
    refetchInterval: 15_000,
  });

export const useAnswerOperatorRequest = (): UseMutationResult<
  null,
  Error,
  AnswerOperatorRequestInput
> => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: answerOperatorRequest,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['operator-requests'] });
    },
  });
};
