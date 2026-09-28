import {
  AutomationFailedError,
  GroupNotFoundError,
  randomChoice,
  SelectorMissingError,
  sleep,
  type AutomationResult,
  type ReactionType,
} from '@fb/shared';
import { shareSelectors } from '../selectors/share.selectors.js';
import { comment } from './comment.js';
import { reactToPost } from './reactToPost.js';
import { openPost } from './postPage.js';
import {
  clearSheet,
  clickPostButton,
  openShareSheet,
  pickSheetOption,
  readRefusal,
} from './shareSheet.js';
import { shareTo } from './sharePost.js';
import { firstVisible, pause, step, throwIfCancelled, type ActionContext } from './types.js';

export interface ShareToGroupInput {
  postUrl: string;
  groupName: string;
  groupUrl: string | null;
  shareToTimeline: boolean;
  reaction: ReactionType | null;
  comments: readonly string[];
}

/**
 * Shares a post into one group through the share sheet's group picker:
 * Share → "Share to a group" → search the group by name → first result →
 * Post. The timeline and story shares, when asked for, come first.
 */
export const shareToGroup = async (
  context: ActionContext,
  input: ShareToGroupInput,
): Promise<AutomationResult> => {
  const startedAt = Date.now();
  const { page, automation } = context;

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 15, 'Opening the post');
  const target = await openPost(context, input.postUrl);

  if (input.shareToTimeline) {
    step(context, 25, 'Sharing to the timeline first');
    await shareTo(context, target, 'timeline');
    throwIfCancelled(context);
    step(context, 35, 'Sharing to the story');
    try {
      await shareTo(context, target, 'story');
    } catch (error) {
      // A story that will not take must not cost the group share.
      context.log(`Story share skipped: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  throwIfCancelled(context);
  step(context, 45, `Sharing to group "${input.groupName}"`);
  if (!(await openShareSheet(context, target))) {
    throw new SelectorMissingError('share button', target.url);
  }

  if ((await pickSheetOption(context, shareSelectors.groupOptions)) === null) {
    await clearSheet(context);
    throw new SelectorMissingError('"Share to a group" option', target.url);
  }

  step(context, 55, 'Searching for the group');
  const dialog = page.locator('[role="dialog"]:visible').last();
  const search = await firstVisible([dialog.locator(shareSelectors.groupSearch)], 10_000);
  if (search === null) {
    await clearSheet(context);
    throw new SelectorMissingError('group search box', target.url);
  }
  await search.scrollIntoViewIfNeeded();
  await search.click();
  await sleep(300);
  await search.fill('');
  await page.keyboard.type(input.groupName, { delay: 50 + Math.random() * 70 });
  await sleep(2_000 + Math.random() * 1_000);

  step(context, 65, 'Picking the first result');
  const escapedName = input.groupName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const result = await firstVisible(
    [
      dialog.getByRole('button', { name: new RegExp(escapedName, 'i') }),
      dialog.locator('a').filter({ hasText: new RegExp(escapedName, 'i') }),
      dialog.getByRole('link', { name: new RegExp(escapedName, 'i') }),
      ...shareSelectors.groupResultContainers.map((selector) => dialog.locator(selector)),
    ],
    10_000,
  );
  if (result === null) {
    await clearSheet(context);
    throw new GroupNotFoundError(input.groupName);
  }

  const chosenName =
    ((await result.innerText().catch(() => '')) || input.groupName).trim().split('\n')[0] ??
    input.groupName;
  await result.scrollIntoViewIfNeeded();
  await sleep(300 + Math.random() * 400);
  await result.click({ force: true });
  await sleep(2_000 + Math.random() * 1_000);

  throwIfCancelled(context);
  step(context, 75, 'Posting');
  if (!(await clickPostButton(context))) {
    await clearSheet(context);
    throw new SelectorMissingError('post button on the group share', target.url);
  }
  await pause(context, 'afterPost');

  const refusal = await readRefusal(context);
  if (refusal !== null && !refusal.transient) {
    throw new AutomationFailedError(refusal.message, { group: chosenName });
  }

  const outcomes: Record<string, unknown> = { group: chosenName, groupUrl: input.groupUrl };

  if (input.reaction !== null) {
    throwIfCancelled(context);
    step(context, 85, `Reacting with ${input.reaction}`);
    await reactToPost(context, { postUrl: target.url, reaction: input.reaction });
    outcomes['reaction'] = input.reaction;
  }

  const chosen = randomChoice(input.comments);
  if (chosen !== null) {
    throwIfCancelled(context);
    step(context, 92, 'Commenting');
    await comment(context, { postUrl: target.url, text: chosen });
    await pause(context, 'afterComment');
    outcomes['comment'] = chosen;
  }

  // The next group is another job for this account. A person does not fire
  // shares back to back; they linger on what they just posted. That linger
  // lives here, inside the job, so nothing else runs on the account meanwhile.
  step(context, 96, 'Lingering before the next share');
  await pause(context, 'betweenShares');

  return {
    resourceUrl: target.url,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: outcomes,
  };
};
