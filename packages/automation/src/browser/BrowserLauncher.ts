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
const PLATFORM =
  process.platform === 'win32'
    ? 'Windows NT 10.0; Win64; x64'
    : process.platform === 'darwin'
      ? 'Macintosh; Intel Mac OS X 10_15_7'
      : 'X11; Linux x86_64';

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
  /** One probe per binary per process: the version string a headless launch must wear. */
  private readonly userAgents = new Map<string, Promise<string>>();

  async launch(options: StartBrowserOptions): Promise<BrowserContext> {
    const binary = this.browserBinary(options);
    try {
      return await chromium.launchPersistentContext(options.userDataDir, {
        headless: options.headless,
        timeout: options.timeoutMs,
        args: LAUNCH_ARGS,
        viewport: { width: 1366, height: 800 },
        ignoreDefaultArgs: ['--enable-automation'],
        ...binary,
        // A background browser must still look like the one a person opens:
        // the full Chromium build rather than the headless shell, and a user
        // agent that does not announce "HeadlessChrome".
        ...(options.headless
          ? {
              ...('channel' in binary || 'executablePath' in binary ? {} : { channel: 'chromium' }),
              userAgent: await this.headlessUserAgent(binary),
            }
          : {}),
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
  /**
   * The user agent the same binary reports when headed, found by asking it
   * once. Headless Chromium otherwise labels itself "HeadlessChrome/…", which
   * is the first thing an anti-bot check reads.
   */
  private headlessUserAgent(binary: Record<string, string>): Promise<string> {
    const key = JSON.stringify(binary);
    const cached = this.userAgents.get(key);
    if (cached !== undefined) return cached;

    const probe = (async (): Promise<string> => {
      const browser = await chromium.launch({
        headless: true,
        ...binary,
        ...('channel' in binary || 'executablePath' in binary ? {} : { channel: 'chromium' }),
      });
      try {
        const version = browser.version();
        return `Mozilla/5.0 (${PLATFORM}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${version} Safari/537.36`;
      } finally {
        await browser.close();
      }
    })();
    // A failed probe is not cached, so the next launch tries again.
    probe.catch(() => this.userAgents.delete(key));
    this.userAgents.set(key, probe);
    return probe;
  }

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
