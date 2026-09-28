import { chromium } from 'playwright';
import { StorageStateSchema, type StorageState } from '@fb/shared';
import type { SessionTransferPort } from '@fb/application';

const PLAYWRIGHT_CHANNELS = new Set(['chrome', 'msedge', 'chrome-beta', 'msedge-beta']);

/**
 * Reads and writes a profile's session as Playwright storage state. Both
 * directions open the profile headless and briefly, without visiting
 * Facebook: the cookies live in the profile whether or not a page loads.
 */
export class SessionTransfer implements SessionTransferPort {
  async exportState(
    userDataDir: string,
    channel: string,
    executablePath: string | null,
  ): Promise<StorageState> {
    const context = await chromium.launchPersistentContext(userDataDir, {
      headless: true,
      ...binary(channel, executablePath),
    });
    try {
      const state = await context.storageState();
      return StorageStateSchema.parse(state);
    } finally {
      await context.close();
    }
  }

  async importState(
    userDataDir: string,
    channel: string,
    executablePath: string | null,
    state: StorageState,
  ): Promise<void> {
    const context = await chromium.launchPersistentContext(userDataDir, {
      headless: true,
      ...binary(channel, executablePath),
    });
    try {
      await context.clearCookies();
      await context.addCookies(state.cookies);

      // localStorage only exists per origin, so each origin is visited once.
      for (const origin of state.origins) {
        if (origin.localStorage.length === 0) continue;
        const page = await context.newPage();
        try {
          await page.goto(origin.origin, { waitUntil: 'commit', timeout: 15_000 });
          await page.evaluate((entries) => {
            for (const entry of entries) localStorage.setItem(entry.name, entry.value);
          }, origin.localStorage);
        } catch {
          // An origin that will not load keeps its cookies and loses its storage; the session usually still works.
        } finally {
          await page.close();
        }
      }
    } finally {
      await context.close();
    }
  }
}

const binary = (channel: string, executablePath: string | null) => {
  if (executablePath !== null && executablePath.length > 0) return { executablePath };
  if (PLAYWRIGHT_CHANNELS.has(channel)) return { channel };
  return {};
};
