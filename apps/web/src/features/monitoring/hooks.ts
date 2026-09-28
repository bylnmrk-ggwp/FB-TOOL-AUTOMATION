import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import type { DashboardStats, ListLogsQuery, LogEntry, Paginated } from '@fb/shared';
import { getDashboard, listLogs } from '../../api/system';

export const useDashboard = (): UseQueryResult<DashboardStats> =>
  useQuery({
    queryKey: ['dashboard'],
    queryFn: ({ signal }) => getDashboard(signal),
    // The socket invalidates this on every change; the interval is only a
    // safety net for a dropped connection.
    refetchInterval: 30_000,
  });

export const useLogs = (query: Partial<ListLogsQuery> = {}): UseQueryResult<Paginated<LogEntry>> =>
  useQuery({
    queryKey: ['logs', query],
    queryFn: ({ signal }) => listLogs(query, signal),
    placeholderData: (previous) => previous,
  });
