import type { Account, AccountStatus } from '@fb/shared';
import { AccountDisabledError } from '@fb/shared';
import { canTransitionAccount } from './AccountStatus.js';

export type { Account };

/** Fields a repository needs in order to insert a new row. */
export interface NewAccount {
  id: string;
  name: string;
  displayName: string;
  profileId: string;
  status: AccountStatus;
  enabled: boolean;
}

export interface AccountPatch {
  name?: string;
  displayName?: string;
  enabled?: boolean;
  status?: AccountStatus;
  lastError?: string | null;
  lastActiveAt?: string | null;
}

export const assertAccountUsable = (account: Account): void => {
  if (!account.enabled) throw new AccountDisabledError(account.id);
};

/**
 * Returns the patch that moves an account to `next`, or null when the move is
 * not part of the lifecycle. Callers decide whether a refused move is an error.
 */
export const accountStatusPatch = (
  account: Account,
  next: AccountStatus,
  reason: string | null = null,
): AccountPatch | null => {
  if (!canTransitionAccount(account.status, next)) return null;
  return {
    status: next,
    lastError: next === 'error' ? reason : null,
  };
};
