export interface ProfileLockInfo {
  profileId: string;
  owner: string;
  acquiredAt: Date;
  expiresAt: Date;
}

export const isLockExpired = (lockedAt: Date, now: Date, ttlMs: number): boolean =>
  now.getTime() - lockedAt.getTime() > ttlMs;

/**
 * Guards a profile directory so two workers cannot drive the same browser data
 * at once. Implemented with both a database row and an on-disk lock file, so a
 * profile stays protected even if the database is reset.
 */
export interface ProfileLockManager {
  acquire(profileId: string, owner: string): Promise<ProfileLockInfo>;
  release(profileId: string, owner: string): Promise<void>;
  /** Removes locks whose holder is gone. Returns the number of locks cleared. */
  reapStale(): Promise<number>;
  isLocked(profileId: string): Promise<boolean>;
}
