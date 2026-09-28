import type { Account, AccountStatus, LoginStatus } from '@fb/shared';
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
  sheetNo?: number | null;
  username?: string | null;
  password?: string | null;
  gmail?: string | null;
  gmailPassword?: string | null;
  phone?: string | null;
  facebookName?: string | null;
}

export interface AccountPatch {
  name?: string;
  displayName?: string;
  enabled?: boolean;
  status?: AccountStatus;
  lastError?: string | null;
  lastActiveAt?: string | null;
  sheetNo?: number | null;
  username?: string | null;
  password?: string | null;
  gmail?: string | null;
  gmailPassword?: string | null;
  phone?: string | null;
  facebookName?: string | null;
  profileUrl?: string | null;
  loginStatus?: LoginStatus;
  loginReason?: string | null;
  lastLoginCheckAt?: string | null;
  shareRestrictedUntil?: string | null;
}

/**
 * The secrets an account signs in with. Read through one repository method
 * and handed only to the login action; never part of an Account view.
 */
export interface AccountCredentials {
  username: string | null;
  password: string | null;
  gmail: string | null;
  gmailPassword: string | null;
}

export const assertAccountUsable = (account: Account): void => {
  if (!account.enabled) throw new AccountDisabledError(account.id);
};

/** True while Facebook's share restriction on the account has not lapsed. */
export const isShareRestricted = (account: Account, now: Date = new Date()): boolean =>
  account.shareRestrictedUntil !== null &&
  new Date(account.shareRestrictedUntil).getTime() > now.getTime();

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
