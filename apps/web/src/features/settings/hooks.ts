import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import type { Settings, SystemPaths, UpdateSettingsInput } from '@fb/shared';
import { getSettings, getSystemPaths, updateSettings } from '../../api/system';

export const useSettings = (): UseQueryResult<Settings> =>
  useQuery({ queryKey: ['settings'], queryFn: ({ signal }) => getSettings(signal) });

export const useSystemPaths = (): UseQueryResult<SystemPaths> =>
  useQuery({
    queryKey: ['system-paths'],
    queryFn: ({ signal }) => getSystemPaths(signal),
    // Paths come from the environment and cannot change while the server runs.
    staleTime: Infinity,
  });

export const useUpdateSettings = (): UseMutationResult<Settings, Error, UpdateSettingsInput> => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateSettings,
    onSuccess: (settings) => {
      queryClient.setQueryData(['settings'], settings);
    },
  });
};
