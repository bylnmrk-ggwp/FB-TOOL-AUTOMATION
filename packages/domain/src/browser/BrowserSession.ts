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
  headless?: boolean;
  /** Identifies the lock owner, usually `${processId}:${sessionId}`. */
  owner: string;
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
}
