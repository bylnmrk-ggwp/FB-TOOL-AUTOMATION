import { EventEmitter } from 'node:events';
import { readFile, stat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { BrowserContext } from 'playwright';
import {
  BrowserAlreadyRunningError,
  BrowserNotRunningError,
  StorageStateSchema,
  type StorageState,
} from '@fb/shared';
import type {
  BrowserController,
  BrowserSession,
  SessionClosedEvent,
  StartBrowserOptions,
} from '@fb/domain';
import type { Logger } from '@fb/application';
import {
  BrowserContextManager,
  LITE_BLOCK,
  NO_BLOCK,
  VIEWER_BLOCK,
} from './BrowserContextManager.js';
import { BrowserLauncher } from './BrowserLauncher.js';
import { Gate } from './Gate.js';
import { SessionTransfer } from './SessionTransfer.js';
import { captureTerminalFrame } from './terminalFrame.js';

/** How many viewers may be starting at the same moment; more only pins the CPU. */
const VIEWER_STARTS_AT_ONCE = 3;
/** A session read out of a profile is reused for this long, unless the profile's cookies changed since. */
const VIEWER_STATE_TTL_MS = 6 * 60 * 60 * 1000;
const VIEWER_STATE_FILE = 'viewer-state.json';

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
  private readonly viewerGate = new Gate(VIEWER_STARTS_AT_ONCE);

  constructor(
    private readonly logger: Logger,
    private readonly launcher = new BrowserLauncher(),
    private readonly contexts = new BrowserContextManager(),
    private readonly transfer = new SessionTransfer(),
  ) {
    this.emitter.setMaxListeners(50);
  }

  async start(options: StartBrowserOptions): Promise<BrowserSession> {
    if (this.sessions.has(options.accountId)) {
      throw new BrowserAlreadyRunningError(options.accountId);
    }

    // A headless viewer does not get a browser of its own: its session is
    // read out of the profile and loaded into a context of the one shared
    // Chromium, which is what lets twenty or thirty watch where ten could.
    // A proxied account keeps its own browser, since the proxy is per launch.
    const sharedViewer =
      options.headless && options.needsMedia === true && options.proxy === undefined;
    if (sharedViewer) {
      this.logger.info('Viewer opened in the shared browser', {
        event: 'browser.viewer',
        accountId: options.accountId,
      });
    }
    const context = sharedViewer
      ? await this.openViewer(options)
      : await this.launcher.launch(options);
    // A headless browser runs lite: no images, media or fonts. It is invisible
    // and usually only signs in, so it needs none of them, and dropping them
    // is what lets more run at once and each finish sooner. A browser that
    // must play a video is the exception: blocked media is a frozen player.
    const block = !options.headless
      ? NO_BLOCK
      : options.needsMedia === true
        ? VIEWER_BLOCK
        : LITE_BLOCK;
    await this.contexts.prepare(context, options.timeoutMs, block);

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

  /**
   * A viewer start is two launches — the profile, to read its session, and
   * the shared browser context — so a batch of twenty starting together
   * pins the CPU and every page times out. A few go at a time, and the
   * session is read from a cache when the profile has not changed since.
   */
  private async openViewer(options: StartBrowserOptions): Promise<BrowserContext> {
    const release = await this.viewerGate.acquire();
    try {
      const state = await this.viewerState(options);
      return await this.launcher.launchViewer(options, state);
    } finally {
      release();
    }
  }

  private async viewerState(options: StartBrowserOptions): Promise<StorageState> {
    const file = join(options.userDataDir, VIEWER_STATE_FILE);
    const cached = await this.freshViewerState(file, options.userDataDir);
    if (cached !== null) return cached;

    const state = await this.transfer.exportState(
      options.userDataDir,
      options.channel,
      options.executablePath,
    );
    await writeFile(file, JSON.stringify(state)).catch(() => undefined);
    return state;
  }

  /** The cached session, when it is younger than the TTL and than the profile's cookie store. */
  private async freshViewerState(file: string, userDataDir: string): Promise<StorageState | null> {
    try {
      const cache = await stat(file);
      if (Date.now() - cache.mtimeMs > VIEWER_STATE_TTL_MS) return null;
      const cookies = await stat(join(userDataDir, 'Default', 'Network', 'Cookies')).catch(
        () => null,
      );
      if (cookies !== null && cookies.mtimeMs > cache.mtimeMs) return null;
      return StorageStateSchema.parse(JSON.parse(await readFile(file, 'utf8')));
    } catch {
      return null;
    }
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

  /**
   * The account's active page as a packed terminal frame, for the live grid.
   * A page mid-navigation can refuse the shot; that is a null, not an error.
   */
  async terminalFrame(accountId: string): Promise<Uint8Array | null> {
    const running = this.sessions.get(accountId);
    if (running === undefined) return null;
    try {
      const page = await this.contexts.activePage(running.context);
      return await captureTerminalFrame(page);
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
