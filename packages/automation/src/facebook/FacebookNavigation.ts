import type { Page } from 'playwright';
import { AutomationTimeoutError, randomDelayMs, sleep } from '@fb/shared';
import { navigationSelectors } from './selectors/navigation.selectors.js';

export interface NavigationOptions {
  timeoutMs: number;
  /** Idle range inserted between steps so the pacing is not machine-perfect. */
  delayRangeMs: readonly [number, number];
}

/**
 * Getting to a page and finding it usable. Facebook greets a fresh profile
 * with cookie banners and permission prompts that sit on top of everything, so
 * "arrived" means more than "navigated".
 */
export class FacebookNavigation {
  constructor(private readonly options: NavigationOptions) {}

  async goto(page: Page, url: string): Promise<void> {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: this.options.timeoutMs });
    } catch {
      // Playwright's own message names the URL already; the typed error is what
      // the retry policy reads.
      throw new AutomationTimeoutError(`navigate to ${url}`, this.options.timeoutMs);
    }

    await this.dismissInterruptions(page);
  }

  /**
   * Clears the overlays that block the first interaction. Each one is optional:
   * a profile that has already accepted cookies never shows the banner.
   */
  async dismissInterruptions(page: Page): Promise<void> {
    const candidates = [navigationSelectors.cookieAccept, navigationSelectors.notificationsDismiss];

    for (const candidate of candidates) {
      const button = page.getByRole(candidate.role, { name: candidate.name }).first();
      try {
        if (await button.isVisible({ timeout: 1_500 })) {
          await button.click({ timeout: 3_000 });
          await this.pause();
        }
      } catch {
        // Not present, which is the common case once a profile is warm.
      }
    }
  }

  /** Waits for the page to settle, without demanding full network idle. */
  async settle(page: Page): Promise<void> {
    try {
      await page.waitForLoadState('domcontentloaded', { timeout: this.options.timeoutMs });
    } catch {
      // A page that never reports the state is still usable often enough that
      // failing here would cost more than it saves.
    }
    await this.pause();
  }

  /** The human-ish gap between two actions. */
  async pause(): Promise<void> {
    const [min, max] = this.options.delayRangeMs;
    await sleep(randomDelayMs(min, max));
  }
}
