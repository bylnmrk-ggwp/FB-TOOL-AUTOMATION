import {
  AutomationFailedError,
  randomChoice,
  ShareRestrictedError,
  sleep,
  type AutomationResult,
  type ReactionType,
  type ShareTarget,
} from '@fb/shared';
import { shareSelectors } from '../selectors/share.selectors.js';
import { comment } from './comment.js';
import { reactToPost } from './reactToPost.js';
import { backOnPost, openPost, type PostTarget } from './postPage.js';
import {
  clearSheet,
  clickPostButton,
  composerOptionOffered,
  openShareSheet,
  pickSheetOption,
  readRefusal,
  sheetStillOpen,
} from './shareSheet.js';
import { pause, step, throwIfCancelled, type ActionContext } from './types.js';

export interface SharePostInput {
  postUrl: string;
  targets: readonly ShareTarget[];
  reaction: ReactionType | null;
  comments: readonly string[];
}

const SHARE_ATTEMPTS = 3;

/**
 * Shares a post to the account's own timeline, story or feed, then reacts and
 * comments if asked. Each target is its own share through the same sheet.
 *
 * A refusal is retried only when Facebook's own message says "try again";
 * a refusal that names the account is a restriction, and repeating it is
 * what gets the account restricted further.
 */
export const sharePost = async (
  context: ActionContext,
  input: SharePostInput,
): Promise<AutomationResult> => {
  const startedAt = Date.now();
  const { page, automation } = context;

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 15, 'Opening the post');
  const target = await openPost(context, input.postUrl);

  const outcomes: Record<string, string> = {};
  let progress = 25;
  for (const shareTarget of input.targets) {
    throwIfCancelled(context);
    step(context, progress, `Sharing to ${shareTarget}`);
    await shareTo(context, target, shareTarget);
    outcomes[shareTarget] = 'shared';
    progress += 20;
  }

  if (input.reaction !== null) {
    throwIfCancelled(context);
    step(context, 80, `Reacting with ${input.reaction}`);
    await reactToPost(context, { postUrl: target.url, reaction: input.reaction });
    outcomes['reaction'] = input.reaction;
  }

  const chosen = randomChoice(input.comments);
  if (chosen !== null) {
    throwIfCancelled(context);
    step(context, 90, 'Commenting');
    await comment(context, { postUrl: target.url, text: chosen });
    await pause(context, 'afterComment');
    outcomes['comment'] = chosen;
  }

  return {
    resourceUrl: target.url,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: outcomes,
  };
};

/** One target, with the retry policy the sheet deserves. */
export const shareTo = async (
  context: ActionContext,
  target: PostTarget,
  where: ShareTarget,
): Promise<void> => {
  const options =
    where === 'story'
      ? shareSelectors.storyOptions
      : where === 'feed'
        ? shareSelectors.composerOptions
        : shareSelectors.timelineOptions;

  let lastRefusal: string | null = null;
  for (let attempt = 1; attempt <= SHARE_ATTEMPTS; attempt += 1) {
    await backOnPost(context, target);

    // From the second attempt a timeline share goes through the composer,
    // which is a different server call: Facebook refused "Share now" three
    // times on a post it accepted through the composer seconds later.
    if (attempt > 1 && where === 'timeline') {
      const composed = await shareViaComposer(context, target);
      if (composed === 'shared') return;
      if (composed === 'failed') {
        const refusal = await readRefusal(context);
        if (refusal !== null && !refusal.transient)
          throw restrictionOrFailure(context, refusal.message);
        await backOnPost(context, target);
      }
    }

    if (await shareOnce(context, target, options, where)) return;

    const refusal = await readRefusal(context);
    lastRefusal = refusal?.message ?? lastRefusal;
    if (refusal !== null && !refusal.transient)
      throw restrictionOrFailure(context, refusal.message);
    if (attempt === SHARE_ATTEMPTS) break;

    const wait = (8_000 + Math.random() * 12_000) * attempt;
    context.log(
      `Facebook said "${lastRefusal ?? 'nothing'}"; retrying in ${Math.round(wait / 1000)}s`,
    );
    await clearSheet(context);
    await sleep(wait);
  }

  throw new AutomationFailedError(
    `Share to ${where} did not land after ${SHARE_ATTEMPTS} attempts${lastRefusal === null ? '' : ` (${lastRefusal})`}`,
    { target: where },
  );
};

const shareOnce = async (
  context: ActionContext,
  target: PostTarget,
  options: readonly string[],
  where: ShareTarget,
): Promise<boolean> => {
  if (!(await openShareSheet(context, target))) {
    context.log('Share button or sheet did not appear');
    return false;
  }

  const picked = await pickSheetOption(context, options);
  if (picked === null) {
    context.log(`No "${options[0]}" option on this sheet`);
    await clearSheet(context);
    return false;
  }

  // The full composer opens on "Share to feed"; press its Post button.
  if (where === 'feed' || shareSelectors.composerOptions.includes(picked as never)) {
    await sleep(2_000);
    if (!(await clickPostButton(context))) return false;
  }

  await pause(context, 'afterPost');
  if (await sheetStillOpen(context)) {
    context.log('The share sheet is still open; the share did not land');
    return false;
  }
  return true;
};

const shareViaComposer = async (
  context: ActionContext,
  target: PostTarget,
): Promise<'shared' | 'failed' | 'unavailable'> => {
  if (!(await openShareSheet(context, target))) return 'failed';

  const option = await composerOptionOffered(context);
  if (option === null) {
    await clearSheet(context);
    return 'unavailable';
  }

  if ((await pickSheetOption(context, [option])) === null) return 'failed';
  await sleep(2_000 + Math.random() * 1_000);
  if (!(await clickPostButton(context))) return 'failed';

  await pause(context, 'afterPost');
  if (await sheetStillOpen(context)) return 'failed';
  await clearSheet(context);
  return 'shared';
};

const restrictionOrFailure = (context: ActionContext, message: string): Error =>
  message.toLowerCase().includes('restrict')
    ? new ShareRestrictedError(context.automation.accountId, null)
    : new AutomationFailedError(message, { refusal: message });
