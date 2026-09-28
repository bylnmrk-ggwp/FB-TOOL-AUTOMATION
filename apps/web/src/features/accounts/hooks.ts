import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import type {
  Account,
  BrowserSessionView,
  CreateAccountInput,
  Job,
  ListAccountsQuery,
  Paginated,
  StorageState,
  UpdateAccountInput,
} from '@fb/shared';
import {
  checkLoginAccounts,
  createAccount,
  deleteAccount,
  importRosterCsv,
  importRosterSheet,
  importSession,
  listAccounts,
  listSessions,
  loginAccounts,
  setAccountEnabled,
  startBrowser,
  stopBrowser,
  updateAccount,
  type RosterImportResult,
} from '../../api/accounts';

export const accountKeys = {
  all: ['accounts'] as const,
  list: (query: Partial<ListAccountsQuery>) => ['accounts', 'list', query] as const,
  sessions: ['sessions'] as const,
};

export const useAccounts = (
  query: Partial<ListAccountsQuery> = {},
): UseQueryResult<Paginated<Account>> =>
  useQuery({
    queryKey: accountKeys.list(query),
    queryFn: ({ signal }) => listAccounts(query, signal),
    // Kept while a new page loads, so the table does not blink on every keystroke.
    placeholderData: (previous) => previous,
  });

export const useSessions = (): UseQueryResult<BrowserSessionView[]> =>
  useQuery({
    queryKey: accountKeys.sessions,
    queryFn: async ({ signal }) => (await listSessions(signal)).sessions,
  });

/** Every account mutation invalidates the same set, so they share one helper. */
const useAccountMutation = <TInput, TResult>(
  mutationFn: (input: TInput) => Promise<TResult>,
): UseMutationResult<TResult, Error, TInput> => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountKeys.all });
      void queryClient.invalidateQueries({ queryKey: accountKeys.sessions });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
};

export const useCreateAccount = (): UseMutationResult<Account, Error, CreateAccountInput> =>
  useAccountMutation(createAccount);

export const useUpdateAccount = (): UseMutationResult<
  Account,
  Error,
  { id: string; patch: UpdateAccountInput }
> =>
  useAccountMutation(({ id, patch }: { id: string; patch: UpdateAccountInput }) =>
    updateAccount(id, patch),
  );

export const useDeleteAccount = (): UseMutationResult<null, Error, string> =>
  useAccountMutation(deleteAccount);

export const useSetAccountEnabled = (): UseMutationResult<
  Account,
  Error,
  { id: string; enabled: boolean }
> =>
  useAccountMutation(({ id, enabled }: { id: string; enabled: boolean }) =>
    setAccountEnabled(id, enabled),
  );

export const useStartBrowser = (): UseMutationResult<BrowserSessionView, Error, string> =>
  useAccountMutation(startBrowser);

export const useStopBrowser = (): UseMutationResult<null, Error, string> =>
  useAccountMutation(stopBrowser);

export const useImportRosterSheet = (): UseMutationResult<RosterImportResult, Error, void> =>
  useAccountMutation(() => importRosterSheet());

export const useImportRosterCsv = (): UseMutationResult<RosterImportResult, Error, string> =>
  useAccountMutation(importRosterCsv);

export const useLoginAccounts = (): UseMutationResult<
  Job[],
  Error,
  { accountIds: string[]; waitForOperator: boolean }
> =>
  useAccountMutation(
    ({ accountIds, waitForOperator }: { accountIds: string[]; waitForOperator: boolean }) =>
      loginAccounts(accountIds, waitForOperator),
  );

export const useCheckLoginAccounts = (): UseMutationResult<Job[], Error, string[]> =>
  useAccountMutation(checkLoginAccounts);

export const useImportSession = (): UseMutationResult<
  null,
  Error,
  { id: string; state: StorageState }
> =>
  useAccountMutation(({ id, state }: { id: string; state: StorageState }) =>
    importSession(id, state),
  );
