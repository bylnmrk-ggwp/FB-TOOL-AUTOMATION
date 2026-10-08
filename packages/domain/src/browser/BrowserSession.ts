import type { AccountStatus } from '@fb/shared';

/**
 * A live browser. This object only ever exists in memory: handles to a running
 * process must never be written to the database.
 */
export interface BrowserSession {
  sessionId: string;
  accountId: string;
  profileId: string;
  status: AccountStatus;
  headless: boolean;
  startedAt: Date;
  currentUrl: string | null;
}

export interface StartBrowserOptions {
  accountId: string;
  sessionId: string;
  profileId: string;
  /** Absolute path to the persistent profile directory. */
  userDataDir: string;
  channel: string;
  executablePath: string | null;
  headless: boolean;
  timeoutMs: number;
  /**
   * Keep images, media and fonts even when headless. A headless browser
   * normally drops them to run lite, but a video cannot play without media.
   */
  needsMedia?: boolean;
  /** The account's proxy, already parsed; every request from this browser goes through it. */
  proxy?: { server: string; username?: string; password?: string };
}

/** Why a session ended, as far as the controller could tell. */
export type SessionClosedReason = 'requested' | 'closed_by_user' | 'crashed';

export interface SessionClosedEvent {
  accountId: string;
  sessionId: string;
  reason: SessionClosedReason;
  message: string | null;
}

/**
 * Infrastructure contract for driving real browsers. The application layer
 * depends on this, never on Playwright.
 */
export interface BrowserController {
  start(options: StartBrowserOptions): Promise<BrowserSession>;
  stop(accountId: string, reason?: string): Promise<void>;
  stopAll(reason?: string): Promise<void>;
  get(accountId: string): BrowserSession | null;
  list(): BrowserSession[];
  isRunning(accountId: string): boolean;
  /** A JPEG of the account's live page, or null when no browser is running. */
  screenshot(accountId: string): Promise<Uint8Array | null>;
  /**
   * The same page as a packed terminal frame (see `packTerminalFrame` in
   * @fb/shared): a few kilobytes, for the live grid. Null when no browser is
   * running or the page refused the shot.
   */
  terminalFrame(accountId: string): Promise<Uint8Array | null>;
  /**
   * Fires when a session ends without being asked to — a crash, or somebody
   * closing the window. The application layer uses it to release the profile
   * lock and correct the account status.
   */
  onClosed(listener: (event: SessionClosedEvent) => void): () => void;
}
