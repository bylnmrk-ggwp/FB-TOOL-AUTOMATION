import {
  AccountSchema,
  BrowserSessionSchema,
  ImportAccountsResultSchema,
  paginatedSchema,
  type Account,
  type BrowserSessionView,
  type CreateAccountInput,
  type ImportAccountsResult,
  type ListAccountsQuery,
  type Paginated,
  type UpdateAccountInput,
} from '@fb/shared';
import { z } from 'zod';
import { apiRequest } from './client';

const AccountPageSchema = paginatedSchema(AccountSchema);

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
