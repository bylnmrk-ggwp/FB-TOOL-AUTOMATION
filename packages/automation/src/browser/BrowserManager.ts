import { EventEmitter } from 'node:events';
import type { BrowserContext } from 'playwright';
import { BrowserAlreadyRunningError, BrowserNotRunningError } from '@fb/shared';
import type {
  BrowserController,
  BrowserSession,
  SessionClosedEvent,
  StartBrowserOptions,
} from '@fb/domain';
import type { Logger } from '@fb/application';
import { BrowserContextManager } from './BrowserContextManager.js';
import { BrowserLauncher } from './BrowserLauncher.js';

const CLOSED = 'closed';

interface RunningSession {
  session: BrowserSession;
  context: BrowserContext;
  /** Set while `stop()` is closing it, so the close event is not a surprise. */
  stopping: boolean;
}

/**
 * The registry of live browsers. It is deliberately in-memory only: a process
 * handle means nothing after a restart, so writing one to the database would
 * only create state that has to be disbelieved later.
 *
 * It knows nothing about accounts, locks or statuses — those belong to the
 * application layer, which is what lets this class be swapped for a fake in
 * tests that have no business launching Chromium.
 */
export class BrowserManager implements BrowserController {
  private readonly sessions = new Map<string, RunningSession>();
  private readonly emitter = new EventEmitter();

  constructor(
    private readonly logger: Logger,
    private readonly launcher = new BrowserLauncher(),
    private readonly contexts = new BrowserContextManager(),
  ) {
    this.emitter.setMaxListeners(50);
  }

  async start(options: StartBrowserOptions): Promise<BrowserSession> {
    if (this.sessions.has(options.accountId)) {
      throw new BrowserAlreadyRunningError(options.accountId);
    }

    const context = await this.launcher.launch(options);
    // A headless browser runs lite: no images, media or fonts. It is invisible
    // and usually only signs in, so it needs none of them, and dropping them
    // is what lets more run at once and each finish sooner. A browser that
    // must play a video is the exception: blocked media is a frozen player.
    const lite = options.headless && options.needsMedia !== true;
    await this.contexts.prepare(context, options.timeoutMs, lite);

    const session: BrowserSession = {
      sessionId: options.sessionId,
      accountId: options.accountId,
      profileId: options.profileId,
      status: 'online',
      headless: options.headless,
      startedAt: new Date(),
      currentUrl: await this.contexts.currentUrl(context),
    };

    const running: RunningSession = { session, context, stopping: false };
    this.sessions.set(options.accountId, running);

    // Playwright fires this for a crash, a user closing the window and our own
    // close alike; `stopping` is what tells the three apart.
    context.on('close', () => {
      this.sessions.delete(options.accountId);
      if (running.stopping) return;

      this.logger.warn('Browser closed unexpectedly', {
        event: 'browser.closed_unexpectedly',
        accountId: options.accountId,
        sessionId: options.sessionId,
      });

      this.emitter.emit(CLOSED, {
        accountId: options.accountId,
        sessionId: options.sessionId,
        reason: 'closed_by_user',
        message: 'The browser window was closed outside the application',
      } satisfies SessionClosedEvent);
    });

    return session;
  }

  async stop(accountId: string, reason = 'requested'): Promise<void> {
    const running = this.sessions.get(accountId);
    if (running === undefined) throw new BrowserNotRunningError(accountId);

    running.stopping = true;
    running.session.status = 'stopping';

    try {
      await running.context.close();
    } catch (error) {
      // A context that refuses to close is already unusable; dropping it from
      // the registry is what matters, so the account can be started again.
      this.logger.warn('Browser did not close cleanly', {
        event: 'browser.close_failed',
        accountId,
        reason: error instanceof Error ? error.message : String(error),
      });
    } finally {
      this.sessions.delete(accountId);
    }

    this.emitter.emit(CLOSED, {
      accountId,
      sessionId: running.session.sessionId,
      reason: 'requested',
      message: reason,
    } satisfies SessionClosedEvent);
  }

  /** Used on shutdown, so no browser outlives the process that opened it. */
  async stopAll(reason = 'server shutting down'): Promise<void> {
    const accountIds = [...this.sessions.keys()];
    await Promise.allSettled(accountIds.map((accountId) => this.stop(accountId, reason)));
  }

  get(accountId: string): BrowserSession | null {
    return this.sessions.get(accountId)?.session ?? null;
  }

  list(): BrowserSession[] {
    return [...this.sessions.values()].map((running) => running.session);
  }

  isRunning(accountId: string): boolean {
    return this.sessions.has(accountId);
  }

  onClosed(listener: (event: SessionClosedEvent) => void): () => void {
    this.emitter.on(CLOSED, listener);
    return () => this.emitter.off(CLOSED, listener);
  }

  /** The live context, for the automation gateway. Null when nothing is open. */
  contextFor(accountId: string): BrowserContext | null {
    return this.sessions.get(accountId)?.context ?? null;
  }

  /**
   * A JPEG of the account's active page, for the live grid. Small and lossy
   * on purpose — it is a thumbnail refreshed every few seconds, not a record.
   * A page mid-navigation can refuse the shot; that is a null, not an error.
   */
  async screenshot(accountId: string): Promise<Uint8Array | null> {
    const running = this.sessions.get(accountId);
    if (running === undefined) return null;
    try {
      const page = await this.contexts.activePage(running.context);
      return await page.screenshot({ type: 'jpeg', quality: 45, timeout: 5_000 });
    } catch {
      return null;
    }
  }

  /** Refreshes the recorded URL, which the Monitor page displays. */
  async refreshUrl(accountId: string): Promise<string | null> {
    const running = this.sessions.get(accountId);
    if (running === undefined) return null;

    const url = await this.contexts.currentUrl(running.context);
    running.session.currentUrl = url;
    return url;
  }

  /** Marks a session busy or idle while a job holds it. */
  setStatus(accountId: string, status: BrowserSession['status']): void {
    const running = this.sessions.get(accountId);
    if (running !== undefined) running.session.status = status;
  }
}
