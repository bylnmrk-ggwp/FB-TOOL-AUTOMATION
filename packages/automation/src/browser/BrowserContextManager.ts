import type { BrowserContext, Page } from 'playwright';
import { STEALTH_INIT_SCRIPT } from './stealth.js';

export interface PreparedContext {
  context: BrowserContext;
  page: Page;
}

/**
 * Everything that has to be true of a context before an action runs: one page
 * to work in, timeouts that match the configured budget, and no dialog left
 * blocking the thread.
 */
/** Request types a login does not need to see; blocking them is memory and speed. */
export const LITE_BLOCK: ReadonlySet<string> = new Set(['image', 'media', 'font']);
/** A viewer needs the video and nothing else that is heavy. */
export const VIEWER_BLOCK: ReadonlySet<string> = new Set(['image', 'font']);
/** A visible browser keeps everything, so a person watching sees a normal page. */
export const NO_BLOCK: ReadonlySet<string> = new Set();

export class BrowserContextManager {
  /**
   * @param block  Request types to drop. A headless login drops images, media
   *   and fonts: it does not look at them, so this both frees the memory each
   *   browser holds and cuts the time a page takes to settle — which is what
   *   lets more run at once and each finish sooner. A viewer drops images and
   *   fonts but keeps media, or the video never plays. A visible browser
   *   drops nothing, so a person watching sees a normal page.
   */
  async prepare(
    context: BrowserContext,
    timeoutMs: number,
    block: ReadonlySet<string> = NO_BLOCK,
  ): Promise<PreparedContext> {
    context.setDefaultTimeout(timeoutMs);
    context.setDefaultNavigationTimeout(timeoutMs);

    if (block.size > 0) {
      await context.route('**/*', (route) => {
        if (block.has(route.request().resourceType())) {
          void route.abort().catch(() => undefined);
        } else {
          void route.continue().catch(() => undefined);
        }
      });
    }

    // Injected before any page script, on every page and frame, so Facebook
    // never sees the automation fingerprint. See stealth.ts for what and why.
    await context.addInitScript(STEALTH_INIT_SCRIPT);

    const existing = context.pages()[0];
    const page = existing ?? (await context.newPage());

    // A persistent profile can restore a session dialog on start-up; leaving
    // one open would stall the first action with no visible cause.
    page.on('dialog', (dialog) => {
      void dialog.dismiss().catch(() => undefined);
    });

    return { context, page };
  }

  /** The page an action should use, reopening one if the profile has none. */
  async activePage(context: BrowserContext): Promise<Page> {
    const open = context.pages().filter((page) => !page.isClosed());
    const first = open[0];
    return first ?? (await context.newPage());
  }

  async currentUrl(context: BrowserContext): Promise<string | null> {
    const open = context.pages().filter((page) => !page.isClosed());
    const first = open[0];
    return first === undefined ? null : first.url();
  }
}
