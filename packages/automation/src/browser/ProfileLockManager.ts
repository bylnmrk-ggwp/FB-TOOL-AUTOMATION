import { readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ProfileLockedError, ProfileNotFoundError } from '@fb/shared';
import type { BrowserProfileRepository, ProfileLockInfo, ProfileLockManager } from '@fb/domain';
import { isLockExpired } from '@fb/domain';
import type { Logger } from '@fb/application';
import type { ProfileManager } from './ProfileManager.js';

const LOCK_FILE = '.fb-automation.lock';

interface LockFileContents {
  owner: string;
  pid: number;
  acquiredAt: string;
}

/**
 * Two guards for one invariant: a profile directory is driven by at most one
 * browser at a time.
 *
 * The database row is the authority — it is what makes the acquire atomic. The
 * file on disk is the witness: it survives a database reset and records which
 * process holds the profile, which is how a lock left behind by a killed
 * process is recognised as dead rather than merely old.
 */
export class FileProfileLockManager implements ProfileLockManager {
  constructor(
    private readonly repository: BrowserProfileRepository,
    private readonly profiles: ProfileManager,
    private readonly logger: Logger,
    private readonly ttlMs: number,
  ) {}

  async acquire(profileId: string, owner: string): Promise<ProfileLockInfo> {
    const profile = await this.repository.findById(profileId);
    if (profile === null) throw new ProfileNotFoundError(profileId);

    const now = new Date();
    const granted = await this.repository.tryAcquireLock(profileId, owner, now, this.ttlMs);

    if (!granted) {
      const holder = (await this.repository.findById(profileId))?.lockedBy ?? 'another worker';
      throw new ProfileLockedError(profileId, holder);
    }

    await this.writeLockFile(profile.slug, owner, now);

    return {
      profileId,
      owner,
      acquiredAt: now,
      expiresAt: new Date(now.getTime() + this.ttlMs),
    };
  }

  async release(profileId: string, owner: string): Promise<void> {
    const profile = await this.repository.findById(profileId);
    await this.repository.releaseLock(profileId, owner);
    if (profile !== null) await this.removeLockFile(profile.slug);
  }

  /**
   * Clears locks whose holder cannot still be alive: the TTL has passed, or the
   * recorded process is this machine's and is gone.
   */
  async reapStale(): Promise<number> {
    const locked = await this.repository.listLocked();
    const now = new Date();
    let cleared = 0;

    for (const profile of locked) {
      const lockedAt = profile.lockedAt === null ? null : new Date(profile.lockedAt);
      const expired = lockedAt === null || isLockExpired(lockedAt, now, this.ttlMs);
      const holderGone = await this.isHolderGone(profile.slug);

      if (!expired && !holderGone) continue;

      await this.repository.update(profile.id, { lockedBy: null, lockedAt: null });
      await this.removeLockFile(profile.slug);
      cleared += 1;

      this.logger.warn('Cleared a stale profile lock', {
        event: 'profile.lock.reaped',
        accountId: profile.accountId,
        profileId: profile.id,
        reason: expired ? 'expired' : 'holder process is gone',
      });
    }

    return cleared;
  }

  async isLocked(profileId: string): Promise<boolean> {
    const profile = await this.repository.findById(profileId);
    if (profile === null || profile.lockedBy === null) return false;
    if (profile.lockedAt === null) return true;
    return !isLockExpired(new Date(profile.lockedAt), new Date(), this.ttlMs);
  }

  /** Called at startup and shutdown so a restart never inherits its own locks. */
  async releaseOwnedBy(owner: string): Promise<number> {
    const held = await this.repository.listLocked();
    const mine = held.filter((profile) => profile.lockedBy === owner);
    for (const profile of mine) await this.removeLockFile(profile.slug);
    return this.repository.releaseLocksOwnedBy(owner);
  }

  private async writeLockFile(slug: string, owner: string, acquiredAt: Date): Promise<void> {
    const contents: LockFileContents = {
      owner,
      pid: process.pid,
      acquiredAt: acquiredAt.toISOString(),
    };
    try {
      await writeFile(this.lockPath(slug), JSON.stringify(contents, null, 2), 'utf8');
    } catch (error) {
      // The database lock is the authority, so a missing witness file is worth
      // a warning but not a failed launch.
      this.logger.warn('Could not write the profile lock file', {
        event: 'profile.lock.file_failed',
        slug,
        reason: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async removeLockFile(slug: string): Promise<void> {
    try {
      await rm(this.lockPath(slug), { force: true });
    } catch {
      // Already gone, which is the state we wanted.
    }
  }

  /**
   * True when the lock file names a process on this machine that no longer
   * exists. A lock written by another machine is never declared dead here —
   * only its TTL can retire it.
   */
  private async isHolderGone(slug: string): Promise<boolean> {
    let parsed: LockFileContents;
    try {
      parsed = JSON.parse(await readFile(this.lockPath(slug), 'utf8')) as LockFileContents;
    } catch {
      return false;
    }

    if (typeof parsed.pid !== 'number') return false;
    if (parsed.pid === process.pid) return false;

    try {
      // Signal 0 performs the permission and existence check without signalling.
      process.kill(parsed.pid, 0);
      return false;
    } catch {
      return true;
    }
  }

  private lockPath(slug: string): string {
    return join(this.profiles.resolve(slug), LOCK_FILE);
  }
}
