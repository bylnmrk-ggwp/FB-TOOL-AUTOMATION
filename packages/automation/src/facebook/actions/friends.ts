import { sleep, type AutomationResult } from '@fb/shared';
import { FRIEND_URLS, friendSelectors } from '../selectors/friends.selectors.js';
import { firstVisible, step, throwIfCancelled, type ActionContext } from './types.js';

/** How many friends the account has, from its own friends page. */
export const countFriends = async (context: ActionContext): Promise<number> => {
  const { page } = context;
  try {
    await page.goto(FRIEND_URLS.myFriends, {
      waitUntil: 'domcontentloaded',
      timeout: context.automation.timeoutMs,
    });
    await sleep(4_000);
    const text = await page.locator('body').innerText();
    const match = friendSelectors.friendsCount.exec(text);
    return match?.[1] === undefined ? 0 : Number.parseInt(match[1].replace(/,/g, ''), 10) || 0;
  } catch {
    return 0;
  }
};

/**
 * Clicks every Confirm/Accept button on the current page, in passes with a
 * scroll between them for lazily loaded rows. Returns how many were clicked.
 */
const clickConfirmButtons = async (context: ActionContext, max: number): Promise<number> => {
  const { page } = context;
  const clickPass = (): Promise<number> =>
    page.evaluate(
      async ({ words, excludes, limit }) => {
        const candidates = [
          ...document.querySelectorAll<HTMLElement>(
            '[role="button"], button, a[role="button"], div[tabindex="0"], span[role="button"]',
          ),
        ];
        const seen = new Set<Element>();
        let clicked = 0;

        for (const element of candidates) {
          if (clicked >= limit) break;
          if (seen.has(element)) continue;
          seen.add(element);

          const text = (element.innerText || '').trim().toLowerCase();
          const aria = (element.getAttribute('aria-label') || '').trim().toLowerCase();
          if (element.offsetParent === null && element.getBoundingClientRect().width === 0)
            continue;
          if (element.getAttribute('aria-disabled') === 'true') continue;

          const matches = words.some(
            (word) => text === word || text.startsWith(word) || aria.includes(word),
          );
          const excluded = excludes.some((word) => text.includes(word) || aria.includes(word));
          if (!matches || excluded) continue;

          element.scrollIntoView({ block: 'center' });
          await new Promise((resolve) => setTimeout(resolve, 300));
          try {
            element.click();
            clicked += 1;
            await new Promise((resolve) => setTimeout(resolve, 500));
          } catch {
            // The next candidate may still take.
          }
        }
        return clicked;
      },
      {
        words: [...friendSelectors.confirmWords],
        excludes: [...friendSelectors.confirmExcludes],
        limit: Math.min(50, max),
      },
    );

  let total = 0;
  for (let pass = 0; pass < 10 && total < max; pass += 1) {
    throwIfCancelled(context);
    const count = await clickPass();
    if (count > 0) {
      total += count;
      await sleep(1_000);
      continue;
    }
    await page.evaluate(() => window.scrollBy(0, 500));
    await sleep(1_000);
    const afterScroll = await clickPass();
    if (afterScroll === 0) break;
    total += afterScroll;
    await sleep(1_000);
  }
  return total;
};

/** Accepts pending friend requests from the requests page. */
export const acceptFriendRequests = async (
  context: ActionContext,
  max: number,
): Promise<number> => {
  const { page } = context;
  let loaded = false;
  for (const url of [FRIEND_URLS.requests, FRIEND_URLS.requestsReceived]) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 25_000 });
      await sleep(3_000);
      if (page.url().includes('facebook')) {
        loaded = true;
        break;
      }
    } catch {
      // Try the next URL.
    }
  }
  if (!loaded) return 0;

  await page.evaluate(() => window.scrollTo(0, 0));
  await sleep(2_000);
  const accepted = await clickConfirmButtons(context, max);

  if (accepted === 0) {
    // Playwright's own locator as a second opinion.
    const buttons = page.getByRole('button', { name: /^confirm$/i });
    const count = await buttons.count();
    let clicked = 0;
    for (let i = 0; i < Math.min(count, max); i += 1) {
      try {
        await buttons.nth(i).click({ timeout: 3_000 });
        clicked += 1;
        await sleep(1_000);
      } catch {
        // Gone by the time it was reached.
      }
    }
    return clicked;
  }
  return accepted;
};

/** Sends friend requests from the suggestions page until `target` are sent. */
export const addFriends = async (context: ActionContext, target: number): Promise<number> => {
  const { page } = context;
  let sent = 0;
  let empty = 0;

  await page.goto(FRIEND_URLS.suggestions, {
    waitUntil: 'domcontentloaded',
    timeout: context.automation.timeoutMs,
  });
  await sleep(3_000);

  for (let round = 0; round < 200 && sent < target; round += 1) {
    throwIfCancelled(context);

    const clicked = await page.evaluate((label) => {
      const candidates = [
        ...document.querySelectorAll<HTMLElement>(
          `div[aria-label="${label}"], span[aria-label="${label}"]`,
        ),
        ...document.querySelectorAll<HTMLElement>('[role="button"], button'),
      ];
      const seen = new Set<Element>();
      let count = 0;
      for (const element of candidates) {
        if (seen.has(element)) continue;
        seen.add(element);
        if (element.offsetParent === null || element.getAttribute('aria-disabled') === 'true')
          continue;
        const text = (element.innerText || '').trim();
        const aria = (element.getAttribute('aria-label') || '').trim();
        if (text !== label && aria !== label) continue;
        element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        count += 1;
        if (count >= 8) break;
      }
      return count;
    }, friendSelectors.addFriend);

    if (clicked > 0) {
      sent += clicked;
      empty = 0;
      context.log(`Sent ${clicked} friend request(s); ${sent} so far`);
      await sleep(2_000 + Math.random() * 2_000);
      continue;
    }

    empty += 1;
    if (empty <= 3) {
      const more = await firstVisible(
        [page.getByRole(friendSelectors.seeMore.role, { name: friendSelectors.seeMore.name })],
        3_000,
      );
      if (more !== null) {
        await more.click({ force: true });
        await sleep(2_000 + Math.random() * 1_000);
        empty = 0;
        continue;
      }
    }
    if (empty >= 5) {
      await page.evaluate(() => window.scrollBy(0, 1200));
      await sleep(1_500 + Math.random() * 1_000);
    }
    if (empty >= 10) {
      context.log('No more suggestions to add');
      break;
    }
  }

  return sent;
};

export const acceptFriendRequestsAction = async (
  context: ActionContext,
  input: { max: number },
): Promise<AutomationResult> => {
  const startedAt = Date.now();
  step(context, 5, 'Checking the session');
  await context.session.assertUsable(context.page, context.automation.accountId);

  step(context, 30, 'Accepting pending requests');
  const accepted = await acceptFriendRequests(context, input.max);
  return {
    resourceUrl: FRIEND_URLS.requests,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { accepted },
  };
};

export const addFriendsAction = async (
  context: ActionContext,
  input: { target: number },
): Promise<AutomationResult> => {
  const startedAt = Date.now();
  step(context, 5, 'Checking the session');
  await context.session.assertUsable(context.page, context.automation.accountId);

  step(context, 30, `Sending up to ${input.target} friend requests`);
  const sent = await addFriends(context, input.target);
  return {
    resourceUrl: FRIEND_URLS.suggestions,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { sent },
  };
};
