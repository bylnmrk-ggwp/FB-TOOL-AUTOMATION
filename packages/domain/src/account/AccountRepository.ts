import type { Account, AccountStatus } from '@fb/shared';
import type { Page, PageRequest } from '../shared/index.js';
import type { AccountPatch, NewAccount } from './Account.js';

export interface AccountFilter extends PageRequest {
  search?: string;
  status?: AccountStatus;
  enabled?: boolean;
}

export interface AccountRepository {
  create(account: NewAccount): Promise<Account>;
  findById(id: string): Promise<Account | null>;
  findByName(name: string): Promise<Account | null>;
  list(filter: AccountFilter): Promise<Page<Account>>;
  update(id: string, patch: AccountPatch): Promise<Account>;
  delete(id: string): Promise<void>;
  countByStatus(): Promise<Record<AccountStatus, number>>;
  /** Used on startup to clear session state left behind by a crash. */
  resetRuntimeStatuses(): Promise<number>;
}
