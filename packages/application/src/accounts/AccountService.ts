import {
  AccountNameTakenError,
  AccountNotFoundError,
  createId,
  nowIso,
  ProfileSlugSchema,
  slugify,
  type Account,
  type AccountCredentialsInput,
  type CreateAccountInput,
  type ImportAccountsResult,
  type RosterRow,
  type UpdateAccountInput,
} from '@fb/shared';
import type { AccountCredentials, AccountFilter, AccountPatch, Page } from '@fb/domain';
import type { EventPublisher } from '../ports/EventPublisher.js';
import type { Logger } from '../ports/Logger.js';
import type { ProfileStorage } from '../ports/ProfileStorage.js';
import type { QueuePort } from '../ports/Queue.js';
import type { Repositories } from '../ports/Repositories.js';

/** The part of the browser layer deletion needs: is one open, and close it. */
export interface SessionControl {
  isRunning(accountId: string): boolean;
  stop(accountId: string, reason?: string): Promise<void>;
}

export interface AccountServiceDeps {
  repositories: Repositories;
  profiles: ProfileStorage;
  events: EventPublisher;
  logger: Logger;
  /** Optional so tests of account CRUD alone need no browser layer. */
  sessions?: SessionControl;
  queue?: QueuePort;
}

/**
 * Turns the writable credential fields into a repository patch. An empty
 * password string means "leave it alone": the edit form cannot show the
 * stored value, so it cannot send it back either.
 */
const credentialPatch = (input: AccountCredentialsInput): AccountPatch => {
  const patch: AccountPatch = {};
  if (input.username !== undefined) patch.username = input.username;
  if (input.gmail !== undefined) patch.gmail = input.gmail;
  if (input.phone !== undefined) patch.phone = input.phone;
  if (input.facebookName !== undefined) patch.facebookName = input.facebookName;
  if (input.sheetNo !== undefined) patch.sheetNo = input.sheetNo;
  if (input.password !== undefined && input.password !== '') patch.password = input.password;
  if (input.gmailPassword !== undefined && input.gmailPassword !== '') {
    patch.gmailPassword = input.gmailPassword;
  }
  return patch;
};

/**
 * The account use cases. Each method is one thing an operator can ask for, and
 * each one owns the whole of that thing: validation, persistence, the
 * filesystem side of the profile, and the event that tells every open browser
 * what changed.
 */
export class AccountService {
  constructor(private deps: AccountServiceDeps) {}

  /**
   * The browser layer and the queue depend on this service for login verdicts,
   * and deletion depends on them to stop what is running. The composition root
   * builds this first and attaches the other two once they exist.
   */
  attach(late: Pick<AccountServiceDeps, 'sessions' | 'queue'>): void {
    this.deps = { ...this.deps, ...late };
  }

  async create(input: CreateAccountInput): Promise<Account> {
    const { repositories, profiles, events, logger } = this.deps;

    const name = input.name.trim();
    if ((await repositories.accounts.findByName(name)) !== null) {
      throw new AccountNameTakenError(name);
    }

    const slug = await this.uniqueSlug(input.profileSlug ?? slugify(name));
    const accountId = createId('acc');
    const profileId = createId('prf');
    const credentials = credentialPatch(input);

    // The directory is created before the rows exist: a half-created account
    // with no profile on disk is harder to reason about than an unused folder.
    await profiles.ensure(slug);

    // The account row comes first — the profile row references it.
    const account = await repositories.accounts.create({
      id: accountId,
      name,
      displayName: (input.displayName ?? name).trim(),
      profileId,
      status: 'offline',
      enabled: input.enabled ?? true,
      sheetNo: credentials.sheetNo ?? null,
      username: credentials.username ?? null,
      password: credentials.password ?? null,
      gmail: credentials.gmail ?? null,
      gmailPassword: credentials.gmailPassword ?? null,
      phone: credentials.phone ?? null,
      facebookName: credentials.facebookName ?? null,
    });

    await repositories.profiles.create({
      id: profileId,
      accountId,
      slug,
      directory: slug,
      channel: 'chromium',
    });

    logger.info('Account created', { event: 'account.created', accountId: account.id });
    events.publish({ type: 'account.created', timestamp: nowIso(), payload: account });
    return account;
  }

  async get(id: string): Promise<Account> {
    const account = await this.deps.repositories.accounts.findById(id);
    if (account === null) throw new AccountNotFoundError(id);
    return account;
  }

  async list(filter: AccountFilter): Promise<Page<Account>> {
    return this.deps.repositories.accounts.list(filter);
  }

  /** Every account the ids name, in one read; a missing id is an error. */
  async requireAll(ids: readonly string[]): Promise<Account[]> {
    const found = await this.deps.repositories.accounts.findByIds(ids);
    const byId = new Map(found.map((account) => [account.id, account]));
    return ids.map((id) => {
      const account = byId.get(id);
      if (account === undefined) throw new AccountNotFoundError(id);
      return account;
    });
  }

  /** Read by the login action only; never returned through the API. */
  async credentials(id: string): Promise<AccountCredentials | null> {
    return this.deps.repositories.accounts.credentials(id);
  }

  async update(id: string, patch: UpdateAccountInput): Promise<Account> {
    const { repositories, events } = this.deps;
    const existing = await this.get(id);

    if (patch.name !== undefined && patch.name.trim() !== existing.name) {
      const clash = await repositories.accounts.findByName(patch.name.trim());
      if (clash !== null) throw new AccountNameTakenError(patch.name.trim());
    }

    const updated = await repositories.accounts.update(id, {
      ...credentialPatch(patch),
      ...(patch.name === undefined ? {} : { name: patch.name.trim() }),
      ...(patch.displayName === undefined ? {} : { displayName: patch.displayName.trim() }),
      ...(patch.enabled === undefined ? {} : { enabled: patch.enabled }),
    });

    events.publish({ type: 'account.updated', timestamp: nowIso(), payload: updated });
    return updated;
  }

  async setEnabled(id: string, enabled: boolean): Promise<Account> {
    const updated = await this.deps.repositories.accounts.update((await this.get(id)).id, {
      enabled,
    });
    this.deps.events.publish({ type: 'account.updated', timestamp: nowIso(), payload: updated });
    return updated;
  }

  /**
   * Removes the account, its jobs and its profile directory.
   *
   * Anything still using the account is stopped first: a running job is asked
   * to abort, and an open browser is closed. A browser holds files inside the
   * profile directory, so deleting underneath it would fail halfway.
   */
  async delete(id: string): Promise<void> {
    const { repositories, profiles, events, logger, sessions, queue } = this.deps;
    const account = await this.get(id);
    const profile = await repositories.profiles.findByAccountId(account.id);

    if (queue !== undefined) {
      for (const job of queue.runningJobs()) {
        if (job.accountId === account.id) queue.requestCancel(job.id);
      }
    }
    if (sessions !== undefined && sessions.isRunning(account.id)) {
      await sessions.stop(account.id, 'account deleted');
    }

    await repositories.jobs.deleteByAccount(account.id);
    await repositories.accounts.delete(account.id);
    if (profile !== null) await repositories.profiles.delete(profile.id);
    if (profile !== null) await profiles.remove(profile.slug);

    logger.info('Account deleted', { event: 'account.deleted', accountId: account.id });
    events.publish({
      type: 'account.deleted',
      timestamp: nowIso(),
      payload: { accountId: account.id },
    });
  }

  /**
   * Bulk import. One bad row does not abort the rest: the caller gets a list of
   * what was skipped and why, which is what an operator importing a spreadsheet
   * actually needs.
   */
  async import(
    accounts: readonly CreateAccountInput[],
    upsert: boolean,
  ): Promise<ImportAccountsResult> {
    const result: ImportAccountsResult = { created: 0, updated: 0, skipped: [] };

    for (const candidate of accounts) {
      const name = candidate.name.trim();
      try {
        const existing = await this.deps.repositories.accounts.findByName(name);

        if (existing === null) {
          await this.create(candidate);
          result.created += 1;
          continue;
        }

        if (!upsert) {
          result.skipped.push({ name, reason: 'An account with this name already exists' });
          continue;
        }

        await this.update(existing.id, {
          ...candidate,
          displayName: candidate.displayName ?? existing.displayName,
          enabled: candidate.enabled ?? existing.enabled,
        });
        result.updated += 1;
      } catch (error) {
        result.skipped.push({
          name,
          reason: error instanceof Error ? error.message : 'Unknown error',
        });
      }
    }

    return result;
  }

  /**
   * Reconciles the roster with the accounts table. The username is the key:
   * a known username has its roster fields refreshed and keeps everything
   * this machine decided — status, profile, login verdict. A new username
   * becomes an account named after the person, with a profile of its own.
   */
  async importRoster(rows: readonly RosterRow[]): Promise<ImportAccountsResult> {
    const result: ImportAccountsResult = { created: 0, updated: 0, skipped: [] };

    for (const row of rows) {
      try {
        const existing = await this.deps.repositories.accounts.findByUsername(row.username);
        const fields: AccountCredentialsInput = {
          sheetNo: row.sheetNo,
          username: row.username,
          facebookName: row.facebookName,
          gmail: row.gmail,
          phone: row.phone,
          // Null on the sheet means "not given", never "clear the stored one".
          ...(row.password === null ? {} : { password: row.password }),
          ...(row.gmailPassword === null ? {} : { gmailPassword: row.gmailPassword }),
        };

        if (existing !== null) {
          await this.update(existing.id, fields);
          result.updated += 1;
          continue;
        }

        const name = await this.uniqueName(row.facebookName ?? row.username);
        await this.create({ name, displayName: row.facebookName ?? name, ...fields });
        result.created += 1;
      } catch (error) {
        result.skipped.push({
          name: row.username,
          reason: error instanceof Error ? error.message : 'Unknown error',
        });
      }
    }

    return result;
  }

  /** Records what a login or login check found. */
  async recordLoginVerdict(
    id: string,
    verdict: Pick<Account, 'loginStatus' | 'loginReason'> & {
      facebookName?: string | null;
      profileUrl?: string | null;
    },
  ): Promise<Account> {
    const updated = await this.deps.repositories.accounts.update(id, {
      loginStatus: verdict.loginStatus,
      loginReason: verdict.loginReason,
      lastLoginCheckAt: nowIso(),
      ...(verdict.facebookName === undefined || verdict.facebookName === null
        ? {}
        : { facebookName: verdict.facebookName }),
      ...(verdict.profileUrl === undefined || verdict.profileUrl === null
        ? {}
        : { profileUrl: verdict.profileUrl }),
    });
    this.deps.events.publish({ type: 'account.updated', timestamp: nowIso(), payload: updated });
    return updated;
  }

  /** Facebook refused a share for this account; hold its share jobs for a while. */
  async recordShareRestriction(id: string, hours: number, reason: string): Promise<Account> {
    const until = new Date(Date.now() + hours * 3_600_000).toISOString();
    const updated = await this.deps.repositories.accounts.update(id, {
      shareRestrictedUntil: until,
      loginReason: reason,
    });
    this.deps.logger.warn(`Share restriction recorded until ${until}`, {
      event: 'account.share_restricted',
      accountId: id,
      reason,
    });
    this.deps.events.publish({ type: 'account.updated', timestamp: nowIso(), payload: updated });
    return updated;
  }

  /** Appends a numeric suffix until the slug is free, so import never collides. */
  private async uniqueSlug(preferred: string): Promise<string> {
    const base = ProfileSlugSchema.parse(slugify(preferred));

    for (let attempt = 0; attempt < 100; attempt += 1) {
      const candidate = attempt === 0 ? base : `${base}-${attempt + 1}`;
      if ((await this.deps.repositories.profiles.findBySlug(candidate)) === null) return candidate;
    }

    return `${base}-${createId('x').slice(-6)}`;
  }

  private async uniqueName(preferred: string): Promise<string> {
    const base = preferred.trim().slice(0, 100) || 'Account';
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const candidate = attempt === 0 ? base : `${base} (${attempt + 1})`;
      if ((await this.deps.repositories.accounts.findByName(candidate)) === null) return candidate;
    }
    return `${base} ${createId('x').slice(-6)}`;
  }
}
