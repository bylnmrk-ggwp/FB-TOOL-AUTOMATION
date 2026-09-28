import type { Account, AccountStatus, LoginStatus } from '@fb/shared';
import type { Page, PageRequest } from '../shared/index.js';
import type { AccountCredentials, AccountPatch, NewAccount } from './Account.js';

export interface AccountFilter extends PageRequest {
  search?: string;
  status?: AccountStatus;
  loginStatus?: LoginStatus;
  enabled?: boolean;
}

export interface AccountRepository {
  create(account: NewAccount): Promise<Account>;
  findById(id: string): Promise<Account | null>;
  findByName(name: string): Promise<Account | null>;
  findByUsername(username: string): Promise<Account | null>;
  findBySheetNo(sheetNo: number): Promise<Account | null>;
  findByIds(ids: readonly string[]): Promise<Account[]>;
  list(filter: AccountFilter): Promise<Page<Account>>;
  update(id: string, patch: AccountPatch): Promise<Account>;
  delete(id: string): Promise<void>;
  countByStatus(): Promise<Record<AccountStatus, number>>;
  countByLoginStatus(): Promise<Record<LoginStatus, number>>;
  /** The only read that returns a password. */
  credentials(id: string): Promise<AccountCredentials | null>;
  /** Used on startup to clear session state left behind by a crash. */
  resetRuntimeStatuses(): Promise<number>;
}
