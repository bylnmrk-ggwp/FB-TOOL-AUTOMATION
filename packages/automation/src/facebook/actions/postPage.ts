import { AutomationBlockedError, AutomationTimeoutError, sleep } from '@fb/shared';
import { shareSelectors } from '../selectors/share.selectors.js';
import { throwIfCancelled, type ActionContext } from './types.js';

export interface PostTarget {
  url: string;
  /** Numeric id from the URL, when it has one; used to find the right article. */
  postId: string | null;
}

const ID_IN_PATH = /\/(?:videos?|posts?|photos?|reels?)\/(\d+)/;
const ID_IN_QUERY = /[?&](?:id|story_fbid)=(\d+)/;

export const postIdFrom = (url: string): string | null =>
  ID_IN_PATH.exec(url)?.[1] ?? ID_IN_QUERY.exec(url)?.[1] ?? null;

/**
 * Opens a post so that its Share button can be pressed: navigates with
 * retries, lets a /share/ interstitial resolve to the real permalink, refuses
 * the account's own post, and scrolls the action row into view.
 */
export const openPost = async (context: ActionContext, url: string): Promise<PostTarget> => {
  const { page, navigation, automation } = context;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: automation.timeoutMs });
      break;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('interrupted by another navigation') && attempt < 2) {
        await sleep(3_000);
        continue;
      }
      throw new AutomationTimeoutError(`open ${url}`, automation.timeoutMs);
    }
  }
  await navigation.dismissInterruptions(page);
  await sleep(2_000 + Math.random() * 2_000);

  // A /share/ link resolves to the real permalink a moment later; wait for it
  // so every later "am I still on the post?" check compares the right URL.
  let target: PostTarget = { url, postId: postIdFrom(url) };
  for (let i = 0; i < 15 && target.postId === null; i += 1) {
    const current = page.url();
    const id = postIdFrom(current);
    if (id !== null) {
      target = { url: current, postId: id };
      break;
    }
    await sleep(1_000);
  }

  throwIfCancelled(context);

  if (await isOwnPost(context)) {
    throw new AutomationBlockedError(
      "This is the account's own post; Facebook does not share those",
    );
  }

  await page.evaluate(
    ({ postId, articleSelector }) => {
      const dialog = document.querySelector('[role="dialog"]');
      if (dialog !== null) {
        dialog.scrollBy(0, 600);
        return;
      }
      const articles = [...document.querySelectorAll(articleSelector)];
      const match =
        (postId === null
          ? undefined
          : articles.find((article) => article.innerHTML.includes(postId))) ?? articles[0];
      if (match !== undefined) match.scrollIntoView({ behavior: 'smooth', block: 'center' });
      else document.documentElement.scrollBy(0, 600);
    },
    { postId: target.postId, articleSelector: shareSelectors.article },
  );
  await sleep(500);

  return target;
};

const isOwnPost = (context: ActionContext): Promise<boolean> =>
  context.page.evaluate((markers) => {
    const buttons = [...document.querySelectorAll<HTMLElement>('[role="button"]')];
    for (const button of buttons) {
      const aria = (button.getAttribute('aria-label') || '').toLowerCase();
      const text = (button.innerText || '').toLowerCase();
      if (aria.includes('edit post') || text.includes('edit post')) return true;
      if (aria === 'edit' && button.offsetParent !== null) return true;
    }
    const body = (document.body.innerText || '').toLowerCase();
    return markers.slice(1).some((marker) => body.includes(marker));
  }, shareSelectors.ownPostMarkers);

/** True when the page is still on the post it started on. */
export const stillOnPost = (context: ActionContext, target: PostTarget): boolean => {
  const current = context.page.url();
  if (target.postId !== null) return current.includes(target.postId);
  return current.split('?')[0] === target.url.split('?')[0];
};

/** Puts the page back on the post when a share moved it elsewhere. */
export const backOnPost = async (context: ActionContext, target: PostTarget): Promise<void> => {
  if (stillOnPost(context, target)) return;
  context.log('Facebook moved away from the post; going back');
  await openPost(context, target.url);
};
