import {
  chromium,
  type Browser,
  type BrowserContext,
  type BrowserContextOptions,
} from 'playwright';
import { BrowserLaunchError, type StorageState } from '@fb/shared';
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
  // The single most-read automation flag; without it navigator.webdriver is
  // true and the "controlled by automated software" state is advertised.
  '--disable-blink-features=AutomationControlled',
  '--disable-features=PasswordLeakDetection,AutofillServerCommunication,IsolateOrigins,site-per-process',
  '--disable-infobars',
];

/**
 * A visible browser gets a real GPU, which removes a WebGL tell. Headless
 * skips it: the init script fakes the WebGL vendor anyway, and a GPU process
 * per browser is memory a batch cannot spare.
 */
const HEADED_ARGS = ['--use-gl=angle', '--use-angle=default'];

/**
 * What a headless browser drops to fit many at once. None of it shows on the
 * page Facebook sees — no window chrome, no extensions, no background chatter,
 * a smaller renderer heap — so twenty lean browsers cost what a handful of
 * default ones would. Images stay: a page with none is its own signal.
 */
const HEADLESS_LEAN_ARGS = [
  '--disable-dev-shm-usage',
  '--disable-extensions',
  '--disable-background-networking',
  '--disable-component-extensions-with-background-pages',
  '--disable-default-apps',
  '--disable-component-update',
  '--disable-sync',
  '--disable-breakpad',
  '--mute-audio',
  '--metrics-recording-only',
  '--no-pings',
  // Caps each renderer's JS heap; a login page needs far less than the default.
  '--js-flags=--max-old-space-size=256',
];

/**
 * What a viewer adds on top of lean: no GPU process at all, and a player that
 * starts without a click. Audio is already muted by the lean set.
 */
const VIEWER_ARGS = ['--disable-gpu', '--autoplay-policy=no-user-gesture-required'];

/** A small window means a small player, and a small player a cheap stream to decode. */
const VIEWER_VIEWPORT = { width: 480, height: 320 };

interface SharedBrowser {
  browser: Browser;
  /** Which binary it runs, so a settings change does not land in the wrong one. */
  key: string;
  contexts: number;
}

/**
 * Turns launch options into a running persistent context. It does one thing,
 * which keeps the interesting part — what a browser session means to the rest
 * of the system — out of Playwright's way.
 */
export class BrowserLauncher {
  /** One probe per binary per process: the version string a headless launch must wear. */
  private readonly userAgents = new Map<string, Promise<string>>();
  /**
   * The one Chromium every headless viewer shares; closed once the last
   * viewer leaves. Held as a promise so ten viewers arriving together wait
   * for one launch instead of each starting a browser of their own.
   */
  private shared: Promise<SharedBrowser> | null = null;
  /** Per binary: whether it decodes H.264, which Facebook video is encoded in. */
  private readonly h264 = new Map<string, Promise<boolean>>();

  async launch(options: StartBrowserOptions): Promise<BrowserContext> {
    const binary =
      options.needsMedia === true ? await this.viewerBinary(options) : this.browserBinary(options);
    try {
      return await chromium.launchPersistentContext(options.userDataDir, {
        headless: options.headless,
        timeout: options.timeoutMs,
        args: [
          ...LAUNCH_ARGS,
          ...(options.headless ? HEADLESS_LEAN_ARGS : HEADED_ARGS),
          ...(options.headless && options.needsMedia === true ? VIEWER_ARGS : []),
        ],
        viewport: options.needsMedia === true ? VIEWER_VIEWPORT : { width: 1366, height: 800 },
        // A locale the timezone and Accept-Language agree with; a missing or
        // mismatched one is itself a signal.
        locale: 'en-US',
        // Every request from this profile leaves through the account's proxy,
        // so its Facebook traffic shares one steady IP.
        ...(options.proxy === undefined ? {} : { proxy: options.proxy }),
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
   * A viewer context inside one shared headless Chromium, built from the
   * account's exported session rather than its profile directory. One browser
   * process then serves every viewer, and each account costs a renderer
   * rather than a whole browser — roughly 100 MB less apiece.
   */
  async launchViewer(options: StartBrowserOptions, state: StorageState): Promise<BrowserContext> {
    const binary = await this.viewerBinary(options);
    try {
      const shared = await this.sharedBrowser(binary, options.timeoutMs);
      const context = await shared.browser.newContext({
        storageState: state as BrowserContextOptions['storageState'],
        viewport: VIEWER_VIEWPORT,
        locale: 'en-US',
        userAgent: await this.headlessUserAgent(binary),
      });
      shared.contexts += 1;
      context.on('close', () => this.releaseShared(shared));
      return context;
    } catch (error) {
      throw new BrowserLaunchError(
        options.accountId,
        error instanceof Error ? error.message : String(error),
        error,
      );
    }
  }

  private async sharedBrowser(
    binary: Record<string, string>,
    timeoutMs: number,
  ): Promise<SharedBrowser> {
    const key = JSON.stringify(binary);
    if (this.shared !== null) {
      const current = await this.shared.catch(() => null);
      if (current !== null && current.key === key && current.browser.isConnected()) return current;
    }

    const launching = (async (): Promise<SharedBrowser> => {
      const browser = await chromium.launch({
        headless: true,
        timeout: timeoutMs,
        args: [...LAUNCH_ARGS, ...HEADLESS_LEAN_ARGS, ...VIEWER_ARGS],
        ignoreDefaultArgs: ['--enable-automation'],
        ...binary,
        ...('channel' in binary || 'executablePath' in binary ? {} : { channel: 'chromium' }),
      });
      const entry: SharedBrowser = { browser, key, contexts: 0 };
      browser.on('disconnected', () => {
        if (this.shared === launching) this.shared = null;
      });
      return entry;
    })();
    // A launch that fails is forgotten, so the next viewer tries again.
    launching.catch(() => {
      if (this.shared === launching) this.shared = null;
    });
    this.shared = launching;
    return launching;
  }

  /**
   * The binary a viewer runs: the configured one when it decodes H.264, and
   * Playwright's own Chromium otherwise. A plain Chromium snapshot ships
   * without H.264, and Facebook then shows "trouble playing this video" in
   * place of a player — so a viewer never uses one, whatever logins use.
   */
  private async viewerBinary(
    options: StartBrowserOptions,
  ): Promise<{ executablePath: string } | { channel: string } | Record<string, never>> {
    const binary = this.browserBinary(options);
    return (await this.decodesH264(binary)) ? binary : {};
  }

  /** Asked once per binary per process: a short headless launch and one question. */
  private decodesH264(binary: Record<string, string>): Promise<boolean> {
    const key = JSON.stringify(binary);
    const cached = this.h264.get(key);
    if (cached !== undefined) return cached;

    const probe = (async (): Promise<boolean> => {
      const browser = await chromium.launch({
        headless: true,
        ...binary,
        ...('channel' in binary || 'executablePath' in binary ? {} : { channel: 'chromium' }),
      });
      try {
        const page = await browser.newPage();
        const answer = await page.evaluate(() =>
          document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E"'),
        );
        return answer !== '';
      } finally {
        await browser.close();
      }
    })();
    // A failed probe is not cached, so the next launch asks again.
    probe.catch(() => this.h264.delete(key));
    this.h264.set(key, probe);
    return probe;
  }

  /** The last viewer out closes the shared browser; nothing idles for ever. */
  private releaseShared(entry: SharedBrowser): void {
    entry.contexts = Math.max(0, entry.contexts - 1);
    if (entry.contexts > 0) return;
    // The disconnected handler clears the slot once the process is gone.
    void entry.browser.close().catch(() => undefined);
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
