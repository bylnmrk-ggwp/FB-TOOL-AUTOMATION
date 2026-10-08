import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import type { AuthSession } from '@fb/shared';
import { getSession } from '../../api/auth';

/** Asked once per page load; the gate refetches it after a login or a 401. */
export const useSession = (): UseQueryResult<AuthSession> =>
  useQuery({
    queryKey: ['auth-session'],
    queryFn: ({ signal }) => getSession(signal),
    staleTime: Infinity,
    retry: 1,
  });
