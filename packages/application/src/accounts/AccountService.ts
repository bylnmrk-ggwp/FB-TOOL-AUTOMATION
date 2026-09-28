import {
  AccountNameTakenError,
  AccountNotFoundError,
  createId,
  nowIso,
  ProfileSlugSchema,
  slugify,
  type Account,
  type CreateAccountInput,
  type ImportAccountsResult,
  type UpdateAccountInput,
} from '@fb/shared';
import type { AccountFilter, Page } from '@fb/domain';
import type { EventPublisher } from '../ports/EventPublisher.js';
import type { Logger } from '../ports/Logger.js';
import type { ProfileStorage } from '../ports/ProfileStorage.js';
import type { Repositories } from '../ports/Repositories.js';

export interface AccountServiceDeps {
  repositories: Repositories;
  profiles: ProfileStorage;
  events: EventPublisher;
  logger: Logger;
}

/**
 * The account use cases. Each method is one thing an operator can ask for, and
 * each one owns the whole of that thing: validation, persistence, the
 * filesystem side of the profile, and the event that tells every open browser
 * what changed.
 */
export class AccountService {
  constructor(private readonly deps: AccountServiceDeps) {}

  async create(input: CreateAccountInput): Promise<Account> {
    const { repositories, profiles, events, logger } = this.deps;

    const name = input.name.trim();
    if ((await repositories.accounts.findByName(name)) !== null) {
      throw new AccountNameTakenError(name);
    }

    const slug = await this.uniqueSlug(input.profileSlug ?? slugify(name));
    const accountId = createId('acc');
    const profileId = createId('prf');

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

  async update(id: string, patch: UpdateAccountInput): Promise<Account> {
    const { repositories, events } = this.deps;
    const existing = await this.get(id);

    if (patch.name !== undefined && patch.name.trim() !== existing.name) {
      const clash = await repositories.accounts.findByName(patch.name.trim());
      if (clash !== null) throw new AccountNameTakenError(patch.name.trim());
    }

    const updated = await repositories.accounts.update(id, {
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
   * Removes the account, its jobs and its profile directory. The caller is
   * responsible for having stopped the browser first; a running session holds
   * the profile lock and would make the directory undeletable anyway.
   */
  async delete(id: string): Promise<void> {
    const { repositories, profiles, events, logger } = this.deps;
    const account = await this.get(id);
    const profile = await repositories.profiles.findByAccountId(account.id);

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

  /** Appends a numeric suffix until the slug is free, so import never collides. */
  private async uniqueSlug(preferred: string): Promise<string> {
    const base = ProfileSlugSchema.parse(slugify(preferred));

    for (let attempt = 0; attempt < 100; attempt += 1) {
      const candidate = attempt === 0 ? base : `${base}-${attempt + 1}`;
      if ((await this.deps.repositories.profiles.findBySlug(candidate)) === null) return candidate;
    }

    return `${base}-${createId('x').slice(-6)}`;
  }
}
