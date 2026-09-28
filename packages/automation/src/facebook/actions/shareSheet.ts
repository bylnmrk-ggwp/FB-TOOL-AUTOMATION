import type { Locator } from 'playwright';
import { sleep } from '@fb/shared';
import { shareSelectors } from '../selectors/share.selectors.js';
import { clickLike } from '../humanInput.js';
import { clickByLabel, firstVisible, pause, type ActionContext } from './types.js';
import type { PostTarget } from './postPage.js';

/** What the share sheet said when a share did not land. */
export interface ShareRefusal {
  message: string;
  transient: boolean;
  restriction: boolean;
}

/**
 * Is the share menu open? Facebook renders it as a dialog, a menu, a bottom
 * sheet, or — on videos and reels — a bare set of buttons on the page, so
 * every pattern is checked in one pass.
 */
export const sheetVisible = (context: ActionContext): Promise<boolean> =>
  context.page.evaluate(() => {
    const shown = (element: Element | null): boolean =>
      element !== null && (element as HTMLElement).offsetParent !== null;
    if (shown(document.querySelector('[role="dialog"]'))) return true;
    if (shown(document.querySelector('[role="menu"]'))) return true;

    const options = [...document.querySelectorAll<HTMLElement>('[role="button"]')]
      .filter((button) => button.offsetParent !== null)
      .map((button) => (button.innerText || '').trim().toLowerCase());
    const known = [
      'share now',
      'your story',
      'copy link',
      "friend's profile",
      'share to a group',
      'send in messenger',
      'embed',
      'copy link to post',
      'send link',
    ];
    if (known.some((label) => options.includes(label))) return true;

    for (const list of document.querySelectorAll<HTMLElement>('[role="listbox"], [role="list"]')) {
      if (list.offsetParent === null) continue;
      const text = (list.innerText || '').toLowerCase();
      if (text.includes('share') || text.includes('story') || text.includes('copy link'))
        return true;
    }
    return false;
  });

/** The Share button of the post — inside its article first, the page second. */
const findShareButton = async (
  context: ActionContext,
  target: PostTarget,
): Promise<Locator | null> => {
  const { page } = context;
  const candidates: Locator[] = [];

  if (target.postId !== null) {
    const article = page
      .locator(shareSelectors.article)
      .filter({ has: page.locator(`[href*="${target.postId}"]`) })
      .first();
    candidates.push(article.getByRole('button', { name: shareSelectors.shareButton.name }));
  }
  candidates.push(
    page
      .locator(shareSelectors.article)
      .first()
      .getByRole('button', { name: shareSelectors.shareButton.name }),
    page.getByRole('button', { name: shareSelectors.shareButton.name }),
  );

  return firstVisible(candidates, 8_000);
};

/** Presses Share and waits for the sheet. Returns false when no sheet appears. */
export const openShareSheet = async (
  context: ActionContext,
  target: PostTarget,
): Promise<boolean> => {
  const button = await findShareButton(context, target);
  if (button === null) return false;

  await clickLike(context.page, button);
  for (let i = 0; i < 20; i += 1) {
    await sleep(250);
    if (await sheetVisible(context)) {
      await pause(context, 'afterShareButton');
      return true;
    }
  }
  return false;
};

/**
 * Clicks one option on the open sheet by its visible text. The first label
 * that exists is the only one clicked: choosing a second after one already
 * took would act twice.
 */
export const pickSheetOption = async (
  context: ActionContext,
  labels: readonly string[],
): Promise<string | null> => {
  const { page } = context;

  for (const label of labels) {
    for (const container of shareSelectors.optionContainers) {
      const option = page
        .locator(container)
        .filter({ hasText: new RegExp(`^\\s*${escape(label)}\\s*$`, 'i') })
        .first();
      try {
        if ((await option.count()) > 0 && (await option.isVisible())) {
          await option.scrollIntoViewIfNeeded();
          await sleep(300 + Math.random() * 400);
          await option.click({ force: true });
          await sleep(2_000 + Math.random() * 1_000);
          return label;
        }
      } catch {
        // Try the next container.
      }
    }
  }

  // Bare buttons on a video's sheet have no container to scope to.
  if (await clickByLabel(page, labels, 'page')) {
    const picked = labels[0] ?? null;
    await sleep(2_000 + Math.random() * 1_000);
    return picked;
  }
  return null;
};

/** Which composer route this sheet offers, without waiting. Null when none. */
export const composerOptionOffered = (context: ActionContext): Promise<string | null> =>
  context.page.evaluate(
    (labels) => {
      const visible = (element: Element): boolean => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      };
      for (const dialog of document.querySelectorAll('[role="dialog"]')) {
        if (!visible(dialog)) continue;
        for (const element of dialog.querySelectorAll<HTMLElement>(
          '[role="menuitem"], [role="button"]',
        )) {
          if (!visible(element)) continue;
          const text = (element.innerText || '').trim().toLowerCase();
          const aria = (element.getAttribute('aria-label') || '').toLowerCase();
          for (const wanted of labels) {
            const lower = wanted.toLowerCase();
            if (text === lower || aria === lower) return wanted;
          }
        }
      }
      return null;
    },
    [...shareSelectors.composerOptions],
  );

/** Presses the composer's Post button, whatever language it is in. */
export const clickPostButton = async (context: ActionContext): Promise<boolean> => {
  const { page } = context;
  if (await clickByLabel(page, shareSelectors.postLabels, 'dialog')) return true;

  // Bottom-most large button that is not Back or Close: the Post button in
  // a sheet whose label the list above does not know.
  await page.evaluate(() => {
    document.querySelector('[role="dialog"]')?.scrollTo(0, 1e9);
  });
  await sleep(500);
  return page.evaluate(() => {
    const buttons = [
      ...document.querySelectorAll<HTMLElement>('[role="button"], button, input[type="submit"]'),
    ]
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        const text = (element.innerText || '').trim().toLowerCase();
        const aria = (element.getAttribute('aria-label') || '').trim().toLowerCase();
        return (
          element.offsetParent !== null &&
          rect.width > 50 &&
          rect.height > 20 &&
          !['back', 'close'].includes(text) &&
          !['back', 'close'].includes(aria) &&
          !(element as HTMLButtonElement).disabled &&
          element.getAttribute('aria-disabled') !== 'true'
        );
      })
      .sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top);
    const first = buttons[0];
    if (first === undefined) return false;
    first.click();
    return true;
  });
};

/** The share sheet is still up, which after a share means it did not land. */
export const sheetStillOpen = async (context: ActionContext): Promise<boolean> => {
  const dialog = context.page.locator('[role="dialog"]:visible').first();
  try {
    if ((await dialog.count()) === 0 || !(await dialog.isVisible())) return false;
    const text = ((await dialog.innerText()) || '').toLowerCase();
    return shareSelectors.sheetStillOpenTexts.some((marker) => text.includes(marker));
  } catch {
    return false;
  }
};

/** Reads any refusal Facebook is showing right now. */
export const readRefusal = async (context: ActionContext): Promise<ShareRefusal | null> => {
  const body = (
    await context.page
      .locator('body')
      .innerText({ timeout: 2_000 })
      .catch(() => '')
  ).toLowerCase();
  const transient = shareSelectors.transientErrorTexts.find((text) => body.includes(text));
  const restriction = shareSelectors.restrictionTexts.find(
    (text) => body.includes(text) && (body.includes('share') || body.includes('post')),
  );
  if (restriction !== undefined) {
    return {
      message: `Facebook is restricting this account from sharing (${restriction})`,
      transient: false,
      restriction: true,
    };
  }
  if (transient !== undefined) return { message: transient, transient: true, restriction: false };
  return null;
};

/** Closes whatever sheet is left open, so the next step starts clean. */
export const clearSheet = async (context: ActionContext): Promise<void> => {
  try {
    await context.page.keyboard.press('Escape');
    await sleep(600);
    if (await sheetStillOpen(context)) {
      await context.page.keyboard.press('Escape');
      await sleep(600);
    }
  } catch {
    // Nothing to close.
  }
};

const escape = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
