import {
  AutomationBlockedError,
  SelectorMissingError,
  sleep,
  type AutomationResult,
} from '@fb/shared';
import type { FetchedGroup } from '@fb/domain';
import { GROUPS_FEED_URL, groupSelectors } from '../selectors/groups.selectors.js';
import { clickLike } from '../humanInput.js';
import { firstVisible, pause, step, throwIfCancelled, type ActionContext } from './types.js';

/**
 * Reads the groups this account belongs to off the groups feed page. Facebook
 * loads the list as the page scrolls, so it is scrolled several times first.
 */
export const fetchGroups = async (context: ActionContext): Promise<AutomationResult> => {
  const startedAt = Date.now();
  const { page, navigation, automation } = context;

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 20, 'Opening the groups page');
  await navigation.goto(page, GROUPS_FEED_URL);
  await sleep(3_000);

  step(context, 40, 'Scrolling to load every group');
  for (let i = 0; i < 10; i += 1) {
    throwIfCancelled(context);
    await page.evaluate(() => window.scrollBy(0, 800));
    await sleep(1_500);
  }

  step(context, 80, 'Reading the list');
  const groups = await page.evaluate(
    ({ selector, ignored }) => {
      const results: Array<{ name: string; url: string }> = [];
      const seen = new Set<string>();
      for (const link of document.querySelectorAll<HTMLAnchorElement>(selector)) {
        const match = /facebook\.com\/groups\/([^/?]+)/.exec(link.href || '');
        if (match === null) continue;
        const slug = match[1] ?? '';
        if (slug === '' || seen.has(slug)) continue;
        seen.add(slug);

        let name = (link.getAttribute('aria-label') || '').trim();
        if (name === '') name = (link.querySelector('span')?.textContent || '').trim();
        if (name === '') name = (link.textContent || '').trim();
        if (name.length < 2 || ignored.includes(name.toLowerCase())) continue;

        results.push({ name, url: `https://www.facebook.com/groups/${slug}/` });
      }
      return results;
    },
    { selector: groupSelectors.groupLink, ignored: [...groupSelectors.ignoredNames] as string[] },
  );

  const fetched: FetchedGroup[] = groups;
  context.log(`Found ${fetched.length} group(s)`);

  return {
    resourceUrl: GROUPS_FEED_URL,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { groups: fetched, count: fetched.length },
  };
};

/**
 * Opens a group and presses Join. Membership, a pending request and a group
 * that wants questions answered are all reported rather than retried.
 */
export const joinGroup = async (
  context: ActionContext,
  input: { groupUrl: string },
): Promise<AutomationResult> => {
  const startedAt = Date.now();
  const { page, navigation, automation } = context;

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 25, 'Opening the group');
  await navigation.goto(page, input.groupUrl);
  await sleep(3_000 + Math.random() * 2_000);

  const already = await firstVisible(
    [
      page.getByRole(groupSelectors.alreadyMember.role, {
        name: groupSelectors.alreadyMember.name,
      }),
    ],
    3_000,
  );
  if (already !== null) {
    return done(input.groupUrl, startedAt, 'member', 'Already a member of this group');
  }

  throwIfCancelled(context);
  step(context, 50, 'Pressing Join');
  const join = await firstVisible(
    [page.getByRole(groupSelectors.joinButton.role, { name: groupSelectors.joinButton.name })],
    10_000,
  );

  if (join === null) {
    const questions = await firstVisible(
      [
        page.getByRole(groupSelectors.answerQuestions.role, {
          name: groupSelectors.answerQuestions.name,
        }),
      ],
      2_000,
    );
    if (questions !== null) {
      throw new AutomationBlockedError('This group asks questions before it lets anyone in');
    }
    throw new SelectorMissingError('join button', input.groupUrl);
  }

  await clickLike(page, join);
  await sleep(3_000 + Math.random() * 2_000);

  const confirm = await firstVisible(
    [
      page
        .locator('[role="dialog"]')
        .getByRole(groupSelectors.confirmJoin.role, { name: groupSelectors.confirmJoin.name }),
    ],
    3_000,
  );
  if (confirm !== null) {
    await confirm.click({ force: true });
    await sleep(2_000 + Math.random() * 2_000);
  }

  step(context, 85, 'Reading the outcome');
  const outcome = await firstVisible(
    [page.getByRole(groupSelectors.joinOutcome.role, { name: groupSelectors.joinOutcome.name })],
    5_000,
  );
  const label =
    outcome === null ? '' : ((await outcome.innerText().catch(() => '')) || '').toLowerCase();

  await pause(context, 'betweenJoins');

  if (label.includes('pending') || label.includes('requested') || label.includes('cancel')) {
    return done(input.groupUrl, startedAt, 'pending', 'Join request sent; waiting for approval');
  }
  return done(input.groupUrl, startedAt, 'joined', 'Joined the group');
};

const done = (
  url: string,
  startedAt: number,
  outcome: string,
  message: string,
): AutomationResult => ({
  resourceUrl: url,
  durationMs: Date.now() - startedAt,
  screenshotPath: null,
  details: { outcome, message },
});
