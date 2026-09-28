import type { Locator, Page } from 'playwright';
import { randomDelayMs, sleep } from '@fb/shared';
import type { AutomationContext, DelayName } from '@fb/domain';
import type { FileStore } from '@fb/application';
import type { FacebookNavigation } from '../FacebookNavigation.js';
import type { FacebookSession } from '../FacebookSession.js';
import { idle } from '../humanInput.js';

/** What every action is handed. Actions never reach outside this. */
export interface ActionContext {
  page: Page;
  navigation: FacebookNavigation;
  session: FacebookSession;
  /** Resolves a media id to a path inside the upload directory. */
  files: FileStore;
  automation: AutomationContext;
  log: (message: string) => void;
}

/**
 * Aborts the action if the job has been cancelled. Called between steps, which
 * is where a cancellation can take effect without leaving a half-typed post.
 */
export const throwIfCancelled = (context: ActionContext): void => {
  if (context.automation.signal.aborted) {
    throw new DOMException('The job was cancelled', 'AbortError');
  }
};

/** Reports a step to the queue, which forwards it to the UI. */
export const step = (context: ActionContext, progress: number, description: string): void => {
  context.log(description);
  context.automation.onProgress(progress, description);
};

/** A random pause from one of the operator's delay ranges. */
export const pause = async (context: ActionContext, name: DelayName): Promise<void> => {
  const settings = context.automation.settings;
  const range: readonly [number, number] = (() => {
    switch (name) {
      case 'betweenShares':
        return [settings.betweenSharesMinMs, settings.betweenSharesMaxMs];
      case 'afterShareButton':
        return [settings.afterShareButtonMinMs, settings.afterShareButtonMaxMs];
      case 'afterPost':
        return [settings.afterPostMinMs, settings.afterPostMaxMs];
      case 'betweenJoins':
        return [settings.betweenJoinsMinMs, settings.betweenJoinsMaxMs];
      case 'afterComment':
        return [settings.afterCommentMinMs, settings.afterCommentMaxMs];
      case 'step':
        return context.automation.delayRangeMs;
    }
  })();

  const ms = randomDelayMs(range[0], range[1]);
  if (ms < 3_000) {
    await sleepUnlessCancelled(context, ms);
    return;
  }

  // A wait long enough to notice is spent the way a person spends it — cursor
  // drifting, page scrolled a little — not as a frozen browser. Scrolling is
  // withheld while a share dialog holds the page.
  context.log(`Waiting ${Math.round(ms / 1000)}s (${name})`);
  await idle(context.page, ms, {
    signal: context.automation.signal,
    scroll: name !== 'afterShareButton' && name !== 'step',
  });
};

/** A sleep that a cancellation cuts short instead of waiting out. */
export const sleepUnlessCancelled = async (context: ActionContext, ms: number): Promise<void> => {
  const { signal } = context.automation;
  const slice = 250;
  let waited = 0;
  while (waited < ms) {
    if (signal.aborted) throw new DOMException('The job was cancelled', 'AbortError');
    const next = Math.min(slice, ms - waited);
    await sleep(next);
    waited += next;
  }
};

/** First visible locator among several candidates, or null. */
export const firstVisible = async (
  candidates: readonly Locator[],
  timeoutMs: number,
): Promise<Locator | null> => {
  const deadline = Date.now() + timeoutMs;
  do {
    for (const candidate of candidates) {
      try {
        const first = candidate.first();
        if ((await first.count()) > 0 && (await first.isVisible())) return first;
      } catch {
        // Detached mid-check; try the next.
      }
    }
    await sleep(250);
  } while (Date.now() < deadline);
  return null;
};

/** Every element whose text or aria-label equals one of `labels`, clicked once. */
export const clickByLabel = async (
  page: Page,
  labels: readonly string[],
  scope: 'dialog' | 'page' = 'dialog',
): Promise<boolean> =>
  page.evaluate(
    ({ wanted, dialogOnly }) => {
      const visible = (element: Element): boolean => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && (element as HTMLElement).offsetParent !== null;
      };
      const roots: Element[] = dialogOnly
        ? [...document.querySelectorAll('[role="dialog"]')].filter(visible)
        : [document.body];
      if (roots.length === 0 && dialogOnly) roots.push(document.body);

      for (const root of roots) {
        const buttons = [
          ...root.querySelectorAll<HTMLElement>(
            '[role="button"], button, [role="menuitem"], input[type="submit"]',
          ),
        ].filter(visible);
        for (const label of wanted) {
          const match = buttons.find((button) => {
            const text = (button.innerText || '').trim().toLowerCase();
            const aria = (button.getAttribute('aria-label') || '').trim().toLowerCase();
            return text === label || aria === label;
          });
          if (
            match !== undefined &&
            !(match as HTMLButtonElement).disabled &&
            match.getAttribute('aria-disabled') !== 'true'
          ) {
            match.click();
            return true;
          }
        }
      }
      return false;
    },
    { wanted: labels.map((label) => label.toLowerCase()), dialogOnly: scope === 'dialog' },
  );
