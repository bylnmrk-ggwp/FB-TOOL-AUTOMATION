import {
  AccountSchema,
  BrowserSessionSchema,
  ImportAccountsResultSchema,
  JobSchema,
  paginatedSchema,
  SessionExportSchema,
  type Account,
  type BrowserSessionView,
  type CreateAccountInput,
  type ImportAccountsResult,
  type Job,
  type ListAccountsQuery,
  type Paginated,
  type SessionExport,
  type StorageState,
  type UpdateAccountInput,
} from '@fb/shared';
import { z } from 'zod';
import { apiRequest } from './client';

const AccountPageSchema = paginatedSchema(AccountSchema);
const JobsSchema = z.object({ jobs: z.array(JobSchema) });
const RosterResultSchema = ImportAccountsResultSchema.extend({ rows: z.number().int().min(0) });
export type RosterImportResult = z.infer<typeof RosterResultSchema>;

export const listAccounts = (
  query: Partial<ListAccountsQuery>,
  signal?: AbortSignal,
): Promise<Paginated<Account>> =>
  apiRequest('/accounts', AccountPageSchema, {
    signal,
    query: {
      limit: query.limit ?? 50,
      offset: query.offset ?? 0,
      search: query.search,
      status: query.status,
      loginStatus: query.loginStatus,
      enabled: query.enabled === undefined ? undefined : String(query.enabled),
    },
  });

export const getAccount = (id: string, signal?: AbortSignal): Promise<Account> =>
  apiRequest(`/accounts/${id}`, AccountSchema, { signal });

export const createAccount = (input: CreateAccountInput): Promise<Account> =>
  apiRequest('/accounts', AccountSchema, { method: 'POST', body: input });

export const updateAccount = (id: string, patch: UpdateAccountInput): Promise<Account> =>
  apiRequest(`/accounts/${id}`, AccountSchema, { method: 'PATCH', body: patch });

export const deleteAccount = (id: string): Promise<null> =>
  apiRequest(`/accounts/${id}`, z.null(), { method: 'DELETE' });

export const setAccountEnabled = (id: string, enabled: boolean): Promise<Account> =>
  apiRequest(`/accounts/${id}/${enabled ? 'enable' : 'disable'}`, AccountSchema, {
    method: 'POST',
  });

export const startBrowser = (id: string): Promise<BrowserSessionView> =>
  apiRequest(`/accounts/${id}/browser/start`, BrowserSessionSchema, { method: 'POST', body: {} });

export const stopBrowser = (id: string): Promise<null> =>
  apiRequest(`/accounts/${id}/browser/stop`, z.null(), { method: 'POST' });

export const listSessions = (signal?: AbortSignal): Promise<{ sessions: BrowserSessionView[] }> =>
  apiRequest('/browser/sessions', z.object({ sessions: z.array(BrowserSessionSchema) }), {
    signal,
  });

export const importAccounts = (
  accounts: CreateAccountInput[],
  upsert: boolean,
): Promise<ImportAccountsResult> =>
  apiRequest('/accounts/import', ImportAccountsResultSchema, {
    method: 'POST',
    body: { accounts, upsert },
  });

/** Pulls the roster from the Google Sheet the server is configured with. */
export const importRosterSheet = (): Promise<RosterImportResult> =>
  apiRequest('/accounts/import/sheet', RosterResultSchema, { method: 'POST', body: {} });

export const importRosterCsv = (csv: string): Promise<RosterImportResult> =>
  apiRequest('/accounts/import/csv', RosterResultSchema, { method: 'POST', body: { csv } });

export const loginAccounts = (accountIds: string[], waitForOperator = true): Promise<Job[]> =>
  apiRequest('/accounts/login', JobsSchema, {
    method: 'POST',
    body: { accountIds, waitForOperator },
  }).then((result) => result.jobs);

export const checkLoginAccounts = (accountIds: string[]): Promise<Job[]> =>
  apiRequest('/accounts/check-login', JobsSchema, { method: 'POST', body: { accountIds } }).then(
    (result) => result.jobs,
  );

export const exportSession = (id: string): Promise<SessionExport> =>
  apiRequest(`/accounts/${id}/session`, SessionExportSchema);

export const importSession = (id: string, state: StorageState): Promise<null> =>
  apiRequest(`/accounts/${id}/session`, z.null(), { method: 'POST', body: { state } });
