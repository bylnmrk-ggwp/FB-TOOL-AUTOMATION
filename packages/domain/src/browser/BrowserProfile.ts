import type { BrowserProfile } from '@fb/shared';

export type { BrowserProfile };

export interface NewBrowserProfile {
  id: string;
  accountId: string;
  slug: string;
  /** Always relative to the configured profile root. */
  directory: string;
  channel: string;
}

export interface BrowserProfilePatch {
  channel?: string;
  lockedBy?: string | null;
  lockedAt?: string | null;
  lastUsedAt?: string | null;
}
