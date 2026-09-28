import { chromium, type BrowserContext } from 'playwright';
import { BrowserLaunchError } from '@fb/shared';
import type { StartBrowserOptions } from '@fb/domain';

/** Playwright channel names. Brave is launched by path, not by channel. */
const PLAYWRIGHT_CHANNELS = new Set(['chrome', 'msedge', 'chrome-beta', 'msedge-beta']);

/**
 * Arguments that make an automated Chromium behave like the browser a person
 * would leave open: no first-run wizard, no password manager prompts, no
 * "Chrome is being controlled by automated software" infobar.
 */
const LAUNCH_ARGS = [
  '--no-first-run',
  '--no-default-browser-check',
  '--disable-blink-features=AutomationControlled',
  '--disable-features=PasswordLeakDetection,AutofillServerCommunication',
  '--disable-infobars',
];

/**
 * Turns launch options into a running persistent context. It does one thing,
 * which keeps the interesting part — what a browser session means to the rest
 * of the system — out of Playwright's way.
 */
export class BrowserLauncher {
  async launch(options: StartBrowserOptions): Promise<BrowserContext> {
    try {
      return await chromium.launchPersistentContext(options.userDataDir, {
        headless: options.headless,
        timeout: options.timeoutMs,
        args: LAUNCH_ARGS,
        viewport: { width: 1366, height: 800 },
        ignoreDefaultArgs: ['--enable-automation'],
        ...this.browserBinary(options),
      });
    } catch (error) {
      throw new BrowserLaunchError(
        options.accountId,
        error instanceof Error ? error.message : String(error),
        error,
      );
    }
  }

  /**
   * An explicit executable always wins — that is how Brave, or any other
   * Chromium build, is used. Otherwise a known channel is named, and failing
   * that Playwright's own Chromium is used.
   */
  private browserBinary(
    options: StartBrowserOptions,
  ): { executablePath: string } | { channel: string } | Record<string, never> {
    if (options.executablePath !== null && options.executablePath.length > 0) {
      return { executablePath: options.executablePath };
    }
    if (PLAYWRIGHT_CHANNELS.has(options.channel)) return { channel: options.channel };
    return {};
  }
}
