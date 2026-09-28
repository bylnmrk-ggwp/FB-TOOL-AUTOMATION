import { and, asc, count, eq, inArray, like, or } from 'drizzle-orm';
import type { Account, AccountStatus, LoginStatus } from '@fb/shared';
import { ACCOUNT_STATUSES, AccountNotFoundError, LOGIN_STATUSES, nowIso } from '@fb/shared';
import type {
  AccountCredentials,
  AccountFilter,
  AccountPatch,
  AccountRepository,
  NewAccount,
  Page,
} from '@fb/domain';
import type { Database } from '../db.js';
import { accounts } from '../schema/accounts.js';
import { toAccount } from './mappers.js';

/** Patch keys that map straight onto a column of the same name. */
const DIRECT_FIELDS = [
  'name',
  'displayName',
  'enabled',
  'status',
  'lastError',
  'lastActiveAt',
  'sheetNo',
  'username',
  'password',
  'gmail',
  'gmailPassword',
  'phone',
  'facebookName',
  'profileUrl',
  'loginStatus',
  'loginReason',
  'lastLoginCheckAt',
  'shareRestrictedUntil',
] as const;

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
      sheetNo: account.sheetNo ?? null,
      username: account.username ?? null,
      password: account.password ?? null,
      gmail: account.gmail ?? null,
      gmailPassword: account.gmailPassword ?? null,
      phone: account.phone ?? null,
      facebookName: account.facebookName ?? null,
      profileUrl: null,
      loginStatus: 'unknown',
      loginReason: null,
      lastLoginCheckAt: null,
      shareRestrictedUntil: null,
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

  async findByUsername(username: string): Promise<Account | null> {
    const rows = await this.db
      .select()
      .from(accounts)
      .where(eq(accounts.username, username))
      .limit(1);
    const row = rows[0];
    return row === undefined ? null : toAccount(row);
  }

  async findByIds(ids: readonly string[]): Promise<Account[]> {
    if (ids.length === 0) return [];
    const rows = await this.db
      .select()
      .from(accounts)
      .where(inArray(accounts.id, [...ids]));
    return rows.map(toAccount);
  }

  async list(filter: AccountFilter): Promise<Page<Account>> {
    const where = this.buildWhere(filter);

    const rows = await this.db
      .select()
      .from(accounts)
      .where(where)
      .orderBy(asc(accounts.sheetNo), asc(accounts.name))
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
    for (const field of DIRECT_FIELDS) {
      if (patch[field] !== undefined) values[field] = patch[field];
    }

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

  async countByLoginStatus(): Promise<Record<LoginStatus, number>> {
    const rows = await this.db
      .select({ status: accounts.loginStatus, value: count() })
      .from(accounts)
      .groupBy(accounts.loginStatus);

    const result = Object.fromEntries(LOGIN_STATUSES.map((status) => [status, 0])) as Record<
      LoginStatus,
      number
    >;
    for (const row of rows) result[row.status] = row.value;
    return result;
  }

  async credentials(id: string): Promise<AccountCredentials | null> {
    const rows = await this.db
      .select({
        username: accounts.username,
        password: accounts.password,
        gmail: accounts.gmail,
        gmailPassword: accounts.gmailPassword,
      })
      .from(accounts)
      .where(eq(accounts.id, id))
      .limit(1);
    return rows[0] ?? null;
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
      const needle = `%${filter.search}%`;
      clauses.push(
        or(
          like(accounts.name, needle),
          like(accounts.displayName, needle),
          like(accounts.username, needle),
          like(accounts.facebookName, needle),
          like(accounts.gmail, needle),
        ),
      );
    }
    if (filter.status !== undefined) clauses.push(eq(accounts.status, filter.status));
    if (filter.loginStatus !== undefined) {
      clauses.push(eq(accounts.loginStatus, filter.loginStatus));
    }
    if (filter.enabled !== undefined) clauses.push(eq(accounts.enabled, filter.enabled));
    return clauses.length === 0 ? undefined : and(...clauses);
  }

  private async require(id: string): Promise<Account> {
    const account = await this.findById(id);
    if (account === null) throw new AccountNotFoundError(id);
    return account;
  }
}
