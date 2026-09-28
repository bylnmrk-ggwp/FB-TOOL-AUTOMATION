import type { AccountStatus } from '@fb/shared';

/**
 * Browser lifecycle for one account. `busy` means a job holds the session.
 *
 *   offline -> starting -> online -> busy -> online -> stopping -> offline
 *                    \                                       /
 *                     +----------------> error <------------+
 */
const ALLOWED: Readonly<Record<AccountStatus, readonly AccountStatus[]>> = {
  offline: ['starting', 'error'],
  starting: ['online', 'error', 'offline'],
  online: ['busy', 'stopping', 'error', 'offline'],
  busy: ['online', 'stopping', 'error'],
  stopping: ['offline', 'error'],
  error: ['starting', 'offline'],
};

export const canTransitionAccount = (from: AccountStatus, to: AccountStatus): boolean =>
  from === to || (ALLOWED[from] ?? []).includes(to);

/** An account is only available for automation when it is idle and online. */
export const isAccountAvailable = (status: AccountStatus): boolean => status === 'online';

export const isBrowserRunning = (status: AccountStatus): boolean =>
  status === 'online' || status === 'busy' || status === 'starting';
