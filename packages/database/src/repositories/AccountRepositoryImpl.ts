import { and, asc, count, eq, inArray, like } from 'drizzle-orm';
import type { Account, AccountStatus } from '@fb/shared';
import { ACCOUNT_STATUSES, AccountNotFoundError, nowIso } from '@fb/shared';
import type { AccountFilter, AccountPatch, AccountRepository, NewAccount, Page } from '@fb/domain';
import type { Database } from '../db.js';
import { accounts } from '../schema/accounts.js';
import { toAccount } from './mappers.js';

export class AccountRepositoryImpl implements AccountRepository {
  constructor(private readonly db: Database) {}

  async create(account: NewAccount): Promise<Account> {
    const now = nowIso();
    await this.db.insert(accounts).values({
      id: account.id,
      name: account.name,
      displayName: account.displayName,
      profileId: account.profileId,
      status: account.status,
      enabled: account.enabled,
      lastError: null,
      lastActiveAt: null,
      createdAt: now,
      updatedAt: now,
    });
    return this.require(account.id);
  }

  async findById(id: string): Promise<Account | null> {
    const rows = await this.db.select().from(accounts).where(eq(accounts.id, id)).limit(1);
    const row = rows[0];
    return row === undefined ? null : toAccount(row);
  }

  async findByName(name: string): Promise<Account | null> {
    const rows = await this.db.select().from(accounts).where(eq(accounts.name, name)).limit(1);
    const row = rows[0];
    return row === undefined ? null : toAccount(row);
  }

  async list(filter: AccountFilter): Promise<Page<Account>> {
    const where = this.buildWhere(filter);

    const rows = await this.db
      .select()
      .from(accounts)
      .where(where)
      .orderBy(asc(accounts.name))
      .limit(filter.limit)
      .offset(filter.offset);

    const totals = await this.db.select({ value: count() }).from(accounts).where(where);

    return {
      items: rows.map(toAccount),
      total: totals[0]?.value ?? 0,
      limit: filter.limit,
      offset: filter.offset,
    };
  }

  async update(id: string, patch: AccountPatch): Promise<Account> {
    const values: Record<string, unknown> = { updatedAt: nowIso() };
    if (patch.name !== undefined) values['name'] = patch.name;
    if (patch.displayName !== undefined) values['displayName'] = patch.displayName;
    if (patch.enabled !== undefined) values['enabled'] = patch.enabled;
    if (patch.status !== undefined) values['status'] = patch.status;
    if (patch.lastError !== undefined) values['lastError'] = patch.lastError;
    if (patch.lastActiveAt !== undefined) values['lastActiveAt'] = patch.lastActiveAt;

    await this.db.update(accounts).set(values).where(eq(accounts.id, id));
    return this.require(id);
  }

  async delete(id: string): Promise<void> {
    await this.db.delete(accounts).where(eq(accounts.id, id));
  }

  async countByStatus(): Promise<Record<AccountStatus, number>> {
    const rows = await this.db
      .select({ status: accounts.status, value: count() })
      .from(accounts)
      .groupBy(accounts.status);

    const result = Object.fromEntries(ACCOUNT_STATUSES.map((status) => [status, 0])) as Record<
      AccountStatus,
      number
    >;

    for (const row of rows) result[row.status] = row.value;
    return result;
  }

  /**
   * No browser survives a restart, so any account left mid-session is put back
   * to `offline` before the queue starts handing out work.
   */
  async resetRuntimeStatuses(): Promise<number> {
    const stale: AccountStatus[] = ['starting', 'online', 'busy', 'stopping'];
    const rows = await this.db
      .select({ id: accounts.id })
      .from(accounts)
      .where(inArray(accounts.status, stale));

    if (rows.length === 0) return 0;

    await this.db
      .update(accounts)
      .set({ status: 'offline', updatedAt: nowIso() })
      .where(inArray(accounts.status, stale));

    return rows.length;
  }

  private buildWhere(filter: AccountFilter) {
    const clauses = [];
    if (filter.search !== undefined) {
      clauses.push(like(accounts.name, `%${filter.search}%`));
    }
    if (filter.status !== undefined) clauses.push(eq(accounts.status, filter.status));
    if (filter.enabled !== undefined) clauses.push(eq(accounts.enabled, filter.enabled));
    return clauses.length === 0 ? undefined : and(...clauses);
  }

  private async require(id: string): Promise<Account> {
    const account = await this.findById(id);
    if (account === null) throw new AccountNotFoundError(id);
    return account;
  }
}
