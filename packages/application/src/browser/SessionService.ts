import {
  AccountNotFoundError,
  BrowserAlreadyRunningError,
  nowIso,
  ProfileNotFoundError,
  type SessionExport,
  type StorageState,
} from '@fb/shared';
import type { BrowserController } from '@fb/domain';
import type { Logger } from '../ports/Logger.js';
import type { ProfileStorage } from '../ports/ProfileStorage.js';
import type { Repositories } from '../ports/Repositories.js';
import type { SessionTransferPort } from '../ports/Sessions.js';

export interface SessionServiceDeps {
  repositories: Repositories;
  controller: BrowserController;
  profiles: ProfileStorage;
  transfer: SessionTransferPort;
  logger: Logger;
}

/**
 * Carries a signed-in session from one machine to another as a file. The
 * file is the session: whoever holds it is signed in. It is handed to the
 * operator once and never written to the log or the database.
 */
export class SessionService {
  constructor(private readonly deps: SessionServiceDeps) {}

  async export(accountId: string): Promise<SessionExport> {
    const { repositories, controller, profiles, transfer, logger } = this.deps;

    const account = await repositories.accounts.findById(accountId);
    if (account === null) throw new AccountNotFoundError(accountId);
    // The profile directory can be opened by one browser at a time.
    if (controller.isRunning(accountId)) throw new BrowserAlreadyRunningError(accountId);

    const profile = await repositories.profiles.findByAccountId(accountId);
    if (profile === null) throw new ProfileNotFoundError(account.profileId);

    const settings = await repositories.settings.read();
    const state = await transfer.exportState(
      await profiles.ensure(profile.slug),
      profile.channel,
      settings.browserExecutablePath,
    );

    logger.info('Session exported', { event: 'session.exported', accountId });
    return { accountId, accountName: account.name, exportedAt: nowIso(), state };
  }

  async import(accountId: string, state: StorageState): Promise<void> {
    const { repositories, controller, profiles, transfer, logger } = this.deps;

    const account = await repositories.accounts.findById(accountId);
    if (account === null) throw new AccountNotFoundError(accountId);
    if (controller.isRunning(accountId)) throw new BrowserAlreadyRunningError(accountId);

    const profile = await repositories.profiles.findByAccountId(accountId);
    if (profile === null) throw new ProfileNotFoundError(account.profileId);

    const settings = await repositories.settings.read();
    await transfer.importState(
      await profiles.ensure(profile.slug),
      profile.channel,
      settings.browserExecutablePath,
      state,
    );

    // An imported session is unverified until a login check says otherwise.
    await repositories.accounts.update(accountId, {
      loginStatus: 'unknown',
      loginReason: 'session imported; not checked yet',
    });
    logger.info('Session imported', { event: 'session.imported', accountId });
  }
}
