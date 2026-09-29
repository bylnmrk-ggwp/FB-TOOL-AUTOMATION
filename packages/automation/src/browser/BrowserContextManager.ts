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
export class BrowserContextManager {
  async prepare(context: BrowserContext, timeoutMs: number): Promise<PreparedContext> {
    context.setDefaultTimeout(timeoutMs);
    context.setDefaultNavigationTimeout(timeoutMs);

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
