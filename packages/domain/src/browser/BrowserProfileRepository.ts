import type { BrowserProfile } from '@fb/shared';
import type { BrowserProfilePatch, NewBrowserProfile } from './BrowserProfile.js';

export interface BrowserProfileRepository {
  create(profile: NewBrowserProfile): Promise<BrowserProfile>;
  findById(id: string): Promise<BrowserProfile | null>;
  findByAccountId(accountId: string): Promise<BrowserProfile | null>;
  findBySlug(slug: string): Promise<BrowserProfile | null>;
  update(id: string, patch: BrowserProfilePatch): Promise<BrowserProfile>;
  delete(id: string): Promise<void>;
  listLocked(): Promise<BrowserProfile[]>;

  /**
   * Takes the lock only if it is free or already expired, in one statement.
   * Returns false when another owner still holds it.
   */
  tryAcquireLock(profileId: string, owner: string, now: Date, ttlMs: number): Promise<boolean>;
  releaseLock(profileId: string, owner: string): Promise<boolean>;
  /** Releases every lock this process owns. Used on shutdown and on startup. */
  releaseLocksOwnedBy(owner: string): Promise<number>;
}
