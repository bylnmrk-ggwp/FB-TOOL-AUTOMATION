import { EventEmitter } from 'node:events';
import type {
  BrowserController,
  BrowserSession,
  SessionClosedEvent,
  StartBrowserOptions,
} from '@fb/domain';

const CLOSED = 'closed';

/**
 * A browser controller that launches nothing. It keeps the same registry and
 * the same close semantics as the real one, so everything above it — locking,
 * status changes, events — is exercised for real without Chromium.
 */
export class FakeBrowserController implements BrowserController {
  private readonly sessions = new Map<string, BrowserSession>();
  private readonly emitter = new EventEmitter();

  /** Set to make the next launch fail, the way a missing binary would. */
  failNextLaunch: Error | null = null;

  async start(options: StartBrowserOptions): Promise<BrowserSession> {
    if (this.failNextLaunch !== null) {
      const error = this.failNextLaunch;
      this.failNextLaunch = null;
      throw error;
    }

    const session: BrowserSession = {
      sessionId: options.sessionId,
      accountId: options.accountId,
      profileId: options.profileId,
      status: 'online',
      headless: options.headless,
      startedAt: new Date(),
      currentUrl: 'about:blank',
    };
    this.sessions.set(options.accountId, session);
    return session;
  }

  async stop(accountId: string, reason = 'requested'): Promise<void> {
    const session = this.sessions.get(accountId);
    this.sessions.delete(accountId);
    if (session === undefined) return;

    this.emitter.emit(CLOSED, {
      accountId,
      sessionId: session.sessionId,
      reason: 'requested',
      message: reason,
    } satisfies SessionClosedEvent);
  }

  async stopAll(reason = 'shutdown'): Promise<void> {
    for (const accountId of [...this.sessions.keys()]) await this.stop(accountId, reason);
  }

  get(accountId: string): BrowserSession | null {
    return this.sessions.get(accountId) ?? null;
  }

  list(): BrowserSession[] {
    return [...this.sessions.values()];
  }

  async screenshot(accountId: string): Promise<Uint8Array | null> {
    return this.isRunning(accountId) ? new Uint8Array([0xff, 0xd8, 0xff]) : null;
  }

  isRunning(accountId: string): boolean {
    return this.sessions.has(accountId);
  }

  onClosed(listener: (event: SessionClosedEvent) => void): () => void {
    this.emitter.on(CLOSED, listener);
    return () => this.emitter.off(CLOSED, listener);
  }

  /** Simulates a crash or somebody closing the window. */
  simulateCrash(accountId: string): void {
    const session = this.sessions.get(accountId);
    if (session === undefined) return;

    this.sessions.delete(accountId);
    this.emitter.emit(CLOSED, {
      accountId,
      sessionId: session.sessionId,
      reason: 'crashed',
      message: 'The browser process exited unexpectedly',
    } satisfies SessionClosedEvent);
  }
}
