import { and, eq, isNotNull, isNull, lt, or } from 'drizzle-orm';
import type { BrowserProfile } from '@fb/shared';
import { nowIso, ProfileNotFoundError } from '@fb/shared';
import type { BrowserProfilePatch, BrowserProfileRepository, NewBrowserProfile } from '@fb/domain';
import type { Database } from '../db.js';
import { browserProfiles } from '../schema/browserProfiles.js';
import { toBrowserProfile } from './mappers.js';

export class BrowserProfileRepositoryImpl implements BrowserProfileRepository {
  constructor(private readonly db: Database) {}

  async create(profile: NewBrowserProfile): Promise<BrowserProfile> {
    const now = nowIso();
    await this.db.insert(browserProfiles).values({
      id: profile.id,
      accountId: profile.accountId,
      slug: profile.slug,
      directory: profile.directory,
      channel: profile.channel,
      lockedBy: null,
      lockedAt: null,
      lastUsedAt: null,
      createdAt: now,
      updatedAt: now,
    });
    return this.require(profile.id);
  }

  async findById(id: string): Promise<BrowserProfile | null> {
    return this.findOne(eq(browserProfiles.id, id));
  }

  async findByAccountId(accountId: string): Promise<BrowserProfile | null> {
    return this.findOne(eq(browserProfiles.accountId, accountId));
  }

  async findBySlug(slug: string): Promise<BrowserProfile | null> {
    return this.findOne(eq(browserProfiles.slug, slug));
  }

  async update(id: string, patch: BrowserProfilePatch): Promise<BrowserProfile> {
    const values: Record<string, unknown> = { updatedAt: nowIso() };
    if (patch.channel !== undefined) values['channel'] = patch.channel;
    if (patch.lockedBy !== undefined) values['lockedBy'] = patch.lockedBy;
    if (patch.lockedAt !== undefined) values['lockedAt'] = patch.lockedAt;
    if (patch.lastUsedAt !== undefined) values['lastUsedAt'] = patch.lastUsedAt;

    await this.db.update(browserProfiles).set(values).where(eq(browserProfiles.id, id));
    return this.require(id);
  }

  async delete(id: string): Promise<void> {
    await this.db.delete(browserProfiles).where(eq(browserProfiles.id, id));
  }

  async listLocked(): Promise<BrowserProfile[]> {
    const rows = await this.db
      .select()
      .from(browserProfiles)
      .where(isNotNull(browserProfiles.lockedBy));
    return rows.map(toBrowserProfile);
  }

  /**
   * One conditional UPDATE decides the race: the row is only written when the
   * lock is free, already ours, or older than the TTL. Two workers asking at
   * the same moment cannot both come away believing they own it.
   */
  async tryAcquireLock(
    profileId: string,
    owner: string,
    now: Date,
    ttlMs: number,
  ): Promise<boolean> {
    const expiryCutoff = new Date(now.getTime() - ttlMs).toISOString();
    const timestamp = now.toISOString();

    await this.db
      .update(browserProfiles)
      .set({ lockedBy: owner, lockedAt: timestamp, updatedAt: timestamp })
      .where(
        and(
          eq(browserProfiles.id, profileId),
          or(
            isNull(browserProfiles.lockedBy),
            eq(browserProfiles.lockedBy, owner),
            isNull(browserProfiles.lockedAt),
            lt(browserProfiles.lockedAt, expiryCutoff),
          ),
        ),
      );

    // The proxy driver reports no row count, so ownership is confirmed by
    // reading the row back rather than trusting `changes`.
    const profile = await this.findById(profileId);
    return profile !== null && profile.lockedBy === owner;
  }

  async releaseLock(profileId: string, owner: string): Promise<boolean> {
    const timestamp = nowIso();
    await this.db
      .update(browserProfiles)
      .set({ lockedBy: null, lockedAt: null, lastUsedAt: timestamp, updatedAt: timestamp })
      .where(and(eq(browserProfiles.id, profileId), eq(browserProfiles.lockedBy, owner)));

    const profile = await this.findById(profileId);
    return profile !== null && profile.lockedBy === null;
  }

  async releaseLocksOwnedBy(owner: string): Promise<number> {
    const held = await this.db
      .select({ id: browserProfiles.id })
      .from(browserProfiles)
      .where(eq(browserProfiles.lockedBy, owner));

    if (held.length === 0) return 0;

    const timestamp = nowIso();
    await this.db
      .update(browserProfiles)
      .set({ lockedBy: null, lockedAt: null, updatedAt: timestamp })
      .where(eq(browserProfiles.lockedBy, owner));

    return held.length;
  }

  private async findOne(where: ReturnType<typeof eq>): Promise<BrowserProfile | null> {
    const rows = await this.db.select().from(browserProfiles).where(where).limit(1);
    const row = rows[0];
    return row === undefined ? null : toBrowserProfile(row);
  }

  private async require(id: string): Promise<BrowserProfile> {
    const profile = await this.findById(id);
    if (profile === null) throw new ProfileNotFoundError(id);
    return profile;
  }
}
