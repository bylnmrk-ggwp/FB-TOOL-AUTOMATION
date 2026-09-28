import { and, asc, count, desc, eq, like, or } from 'drizzle-orm';
import type { Activity, ActivityKind, Group, GroupSummary } from '@fb/shared';
import { createId, nowIso } from '@fb/shared';
import type {
  ActivityRepository,
  FetchedGroup,
  GroupFilter,
  GroupRepository,
  NewActivity,
  Page,
} from '@fb/domain';
import type { Database } from '../db.js';
import type { SqliteConnection } from '../connection.js';
import { accountActivity, groups } from '../schema/groups.js';
import { toActivity, toGroup } from './mappers.js';

export class GroupRepositoryImpl implements GroupRepository {
  constructor(
    private readonly db: Database,
    private readonly connection: SqliteConnection,
  ) {}

  async list(filter: GroupFilter): Promise<Page<Group>> {
    const where = this.buildWhere(filter);

    const rows = await this.db
      .select()
      .from(groups)
      .where(where)
      .orderBy(asc(groups.name))
      .limit(filter.limit)
      .offset(filter.offset);
    const totals = await this.db.select({ value: count() }).from(groups).where(where);

    return {
      items: rows.map(toGroup),
      total: totals[0]?.value ?? 0,
      limit: filter.limit,
      offset: filter.offset,
    };
  }

  async summaries(): Promise<GroupSummary[]> {
    const rows = await this.db.select().from(groups).orderBy(asc(groups.name));
    const byUrl = new Map<string, GroupSummary>();

    for (const row of rows) {
      const existing = byUrl.get(row.url);
      if (existing === undefined) {
        byUrl.set(row.url, { url: row.url, name: row.name, accountIds: [row.accountId] });
      } else if (!existing.accountIds.includes(row.accountId)) {
        existing.accountIds.push(row.accountId);
      }
    }

    return [...byUrl.values()];
  }

  /**
   * Delete-then-insert inside one transaction: a fetch that finds nothing
   * empties the list rather than leaving yesterday's groups looking current.
   */
  async replaceForAccount(accountId: string, fetched: readonly FetchedGroup[]): Promise<number> {
    return this.connection.transaction(async () => {
      await this.db.delete(groups).where(eq(groups.accountId, accountId));
      if (fetched.length === 0) return 0;

      const now = nowIso();
      const seen = new Set<string>();
      const rows = [];
      for (const group of fetched) {
        if (seen.has(group.url)) continue;
        seen.add(group.url);
        rows.push({
          id: createId('grp'),
          accountId,
          name: group.name,
          url: group.url,
          fetchedAt: now,
        });
      }

      await this.db.insert(groups).values(rows);
      return rows.length;
    });
  }

  async deleteByAccount(accountId: string): Promise<number> {
    const doomed = await this.db
      .select({ id: groups.id })
      .from(groups)
      .where(eq(groups.accountId, accountId));
    if (doomed.length === 0) return 0;
    await this.db.delete(groups).where(eq(groups.accountId, accountId));
    return doomed.length;
  }

  private buildWhere(filter: GroupFilter) {
    const clauses = [];
    if (filter.accountId !== undefined) clauses.push(eq(groups.accountId, filter.accountId));
    if (filter.search !== undefined) {
      const needle = `%${filter.search}%`;
      clauses.push(or(like(groups.name, needle), like(groups.url, needle)));
    }
    return clauses.length === 0 ? undefined : and(...clauses);
  }
}

export class ActivityRepositoryImpl implements ActivityRepository {
  constructor(private readonly db: Database) {}

  async record(activity: NewActivity): Promise<Activity> {
    const existing = await this.find(activity.accountId, activity.kind, activity.targetUrl);
    const createdAt = nowIso();

    if (existing !== null) {
      await this.db
        .update(accountActivity)
        .set({
          status: activity.status,
          message: activity.message,
          jobId: activity.jobId,
          targetName: activity.targetName ?? existing.targetName,
          createdAt,
        })
        .where(eq(accountActivity.id, existing.id));
      const updated = await this.find(activity.accountId, activity.kind, activity.targetUrl);
      if (updated === null) throw new Error('Activity vanished while being updated');
      return updated;
    }

    await this.db.insert(accountActivity).values({
      id: activity.id,
      accountId: activity.accountId,
      kind: activity.kind,
      targetUrl: activity.targetUrl,
      targetName: activity.targetName,
      status: activity.status,
      message: activity.message,
      jobId: activity.jobId,
      createdAt,
    });

    const created = await this.find(activity.accountId, activity.kind, activity.targetUrl);
    if (created === null) throw new Error('Activity vanished while being written');
    return created;
  }

  async find(accountId: string, kind: ActivityKind, targetUrl: string): Promise<Activity | null> {
    const rows = await this.db
      .select()
      .from(accountActivity)
      .where(
        and(
          eq(accountActivity.accountId, accountId),
          eq(accountActivity.kind, kind),
          eq(accountActivity.targetUrl, targetUrl),
        ),
      )
      .limit(1);
    const row = rows[0];
    return row === undefined ? null : toActivity(row);
  }

  async doneTargets(accountId: string, kind: ActivityKind): Promise<Set<string>> {
    const rows = await this.db
      .select({ targetUrl: accountActivity.targetUrl })
      .from(accountActivity)
      .where(
        and(
          eq(accountActivity.accountId, accountId),
          eq(accountActivity.kind, kind),
          eq(accountActivity.status, 'done'),
        ),
      );
    return new Set(rows.map((row) => row.targetUrl));
  }

  async listForAccount(accountId: string, limit: number): Promise<Activity[]> {
    const rows = await this.db
      .select()
      .from(accountActivity)
      .where(eq(accountActivity.accountId, accountId))
      .orderBy(desc(accountActivity.createdAt))
      .limit(limit);
    return rows.map(toActivity);
  }

  async deleteByAccount(accountId: string): Promise<number> {
    const doomed = await this.db
      .select({ id: accountActivity.id })
      .from(accountActivity)
      .where(eq(accountActivity.accountId, accountId));
    if (doomed.length === 0) return 0;
    await this.db.delete(accountActivity).where(eq(accountActivity.accountId, accountId));
    return doomed.length;
  }
}
