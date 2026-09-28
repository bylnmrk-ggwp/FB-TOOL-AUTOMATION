import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import type { Health } from '@fb/shared';
import { fetchHealth } from '../api/health';

export const healthQueryKey = ['health'] as const;

export const useHealth = (): UseQueryResult<Health> =>
  useQuery({
    queryKey: healthQueryKey,
    queryFn: ({ signal }) => fetchHealth(signal),
    refetchInterval: 10_000,
    retry: 1,
  });
