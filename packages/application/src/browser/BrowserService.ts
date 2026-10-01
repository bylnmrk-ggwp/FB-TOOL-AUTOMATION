import {
  AccountDisabledError,
  AccountNotFoundError,
  BrowserAlreadyRunningError,
  BrowserNotRunningError,
  createId,
  nowIso,
  parseProxy,
  ProfileNotFoundError,
  type AccountStatus,
  type BrowserSessionView,
} from '@fb/shared';
import type {
  BrowserController,
  BrowserSession,
  ProfileLockManager,
  SessionClosedEvent,
} from '@fb/domain';
import type { EventPublisher } from '../ports/EventPublisher.js';
import type { Logger } from '../ports/Logger.js';
import type { ProfileStorage } from '../ports/ProfileStorage.js';
import type { Repositories } from '../ports/Repositories.js';

export interface BrowserServiceDeps {
  repositories: Repositories;
  controller: BrowserController;
  locks: ProfileLockManager;
  profiles: ProfileStorage;
  events: EventPublisher;
  logger: Logger;
  /** Identifies this process as the lock owner. */
  workerId: string;
}

const toView = (session: BrowserSession): BrowserSessionView => ({
  accountId: session.accountId,
  sessionId: session.sessionId,
  status: session.status,
  headless: session.headless,
  startedAt: session.startedAt.toISOString(),
  currentUrl: session.currentUrl,
});

/**
 * Starting a browser is four things that must happen in order and unwind
 * correctly: check the account, take the profile lock, launch, record the new
 * status. This class owns that order — the controller below it only launches,
 * and the HTTP layer above it only asks.
 */
export class BrowserService {
  private detach: (() => void) | null = null;

  constructor(private readonly deps: BrowserServiceDeps) {}

  /** Wires crash handling. Called once, by the composition root. */
  listen(): void {
    if (this.detach !== null) return;
    this.detach = this.deps.controller.onClosed((event) => {
      void this.handleClosed(event);
    });
  }

  stopListening(): void {
    this.detach?.();
    this.detach = null;
  }

  async start(
    accountId: string,
    headless?: boolean,
    needsMedia = false,
  ): Promise<BrowserSessionView> {
    const { repositories, controller, locks, profiles, events, logger, workerId } = this.deps;

    // Settings are read per launch, so a change on the Settings page applies to
    // the next browser rather than the next restart.
    const settings = await repositories.settings.read();

    const account = await repositories.accounts.findById(accountId);
    if (account === null) throw new AccountNotFoundError(accountId);
    if (!account.enabled) throw new AccountDisabledError(accountId);

    // Checked before the lock so a second request gets the reason it actually
    // failed, rather than a lock conflict against this very process.
    if (controller.isRunning(accountId)) throw new BrowserAlreadyRunningError(accountId);

    const profile = await repositories.profiles.findByAccountId(accountId);
    if (profile === null) throw new ProfileNotFoundError(account.profileId);

    // Read separately: the proxy string carries a password, so it lives with
    // the credentials the API never returns, not on the account view.
    const credentials = await repositories.accounts.credentials(accountId);
    const proxy = parseProxy(credentials?.proxyUrl ?? null);

    const sessionId = createId('ses');
    const owner = `${workerId}:${sessionId}`;

    await this.setStatus(account.id, 'starting', null);
    await locks.acquire(profile.id, owner);

    try {
      const userDataDir = await profiles.ensure(profile.slug);
      const session = await controller.start({
        accountId: account.id,
        sessionId,
        profileId: profile.id,
        userDataDir,
        channel: profile.channel === '' ? settings.browserChannel : profile.channel,
        executablePath: settings.browserExecutablePath,
        headless: headless ?? settings.headless,
        timeoutMs: settings.defaultTimeoutMs,
        ...(needsMedia ? { needsMedia: true } : {}),
        ...(proxy === null ? {} : { proxy }),
      });

      await this.setStatus(account.id, 'online', null);
      await repositories.profiles.update(profile.id, { lastUsedAt: nowIso() });

      logger.info('Browser started', {
        event: 'browser.started',
        accountId: account.id,
        sessionId,
      });
      events.publish({ type: 'browser.started', timestamp: nowIso(), payload: toView(session) });

      return toView(session);
    } catch (error) {
      // The lock is released on the way out: leaving it held would make the
      // account unusable until the TTL expired.
      await locks.release(profile.id, owner);
      const message = error instanceof Error ? error.message : String(error);
      await this.setStatus(account.id, 'error', message);

      events.publish({
        type: 'browser.error',
        timestamp: nowIso(),
        payload: { accountId: account.id, code: 'BROWSER_LAUNCH_FAILED', message },
      });
      throw error;
    }
  }

  async stop(accountId: string, reason = 'requested'): Promise<void> {
    const { controller, repositories, events, logger } = this.deps;

    const session = controller.get(accountId);
    if (session === null) throw new BrowserNotRunningError(accountId);

    await this.setStatus(accountId, 'stopping', null);
    await controller.stop(accountId, reason);
    await this.releaseLock(session);
    await this.setStatus(accountId, 'offline', null);

    await repositories.profiles.update(session.profileId, { lastUsedAt: nowIso() });

    logger.info('Browser stopped', {
      event: 'browser.stopped',
      accountId,
      sessionId: session.sessionId,
    });
    events.publish({
      type: 'browser.stopped',
      timestamp: nowIso(),
      payload: { accountId, sessionId: session.sessionId, reason },
    });
  }

  /** Called on shutdown: closes every browser and hands back every lock. */
  async stopAll(reason = 'server shutting down'): Promise<void> {
    for (const session of this.deps.controller.list()) {
      try {
        await this.stop(session.accountId, reason);
      } catch (error) {
        this.deps.logger.warn('Could not stop a browser during shutdown', {
          event: 'browser.stop_failed',
          accountId: session.accountId,
          reason: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  get(accountId: string): BrowserSessionView | null {
    const session = this.deps.controller.get(accountId);
    return session === null ? null : toView(session);
  }

  list(): BrowserSessionView[] {
    return this.deps.controller.list().map(toView);
  }

  isRunning(accountId: string): boolean {
    return this.deps.controller.isRunning(accountId);
  }

  /** A JPEG of the account's live page for the grid, or null if none is open. */
  screenshot(accountId: string): Promise<Uint8Array | null> {
    return this.deps.controller.screenshot(accountId);
  }

  /**
   * A browser that went away on its own still has to leave the system tidy:
   * the lock goes back, the account stops claiming to be online, and the UI is
   * told why.
   */
  private async handleClosed(event: SessionClosedEvent): Promise<void> {
    if (event.reason === 'requested') return;

    const { repositories, events, logger } = this.deps;
    const profile = await repositories.profiles.findByAccountId(event.accountId);
    if (profile !== null) {
      await this.deps.locks.release(profile.id, `${this.deps.workerId}:${event.sessionId}`);
    }

    await this.setStatus(event.accountId, 'offline', event.message);

    logger.warn('Browser session ended on its own', {
      event: 'browser.session_lost',
      accountId: event.accountId,
      sessionId: event.sessionId,
      reason: event.reason,
    });

    events.publish({
      type: 'browser.stopped',
      timestamp: nowIso(),
      payload: {
        accountId: event.accountId,
        sessionId: event.sessionId,
        reason: event.message ?? event.reason,
      },
    });
  }

  private async releaseLock(session: BrowserSession): Promise<void> {
    await this.deps.locks.release(session.profileId, `${this.deps.workerId}:${session.sessionId}`);
  }

  /** Writes the new status and announces the change in one place. */
  private async setStatus(
    accountId: string,
    status: AccountStatus,
    reason: string | null,
  ): Promise<void> {
    const before = await this.deps.repositories.accounts.findById(accountId);
    if (before === null) return;

    const updated = await this.deps.repositories.accounts.update(accountId, {
      status,
      lastError: status === 'error' ? reason : null,
      ...(status === 'online' ? { lastActiveAt: nowIso() } : {}),
    });

    this.deps.events.publish({
      type: 'account.status.changed',
      timestamp: nowIso(),
      payload: {
        accountId,
        status: updated.status,
        previousStatus: before.status,
        reason,
      },
    });
  }
}
