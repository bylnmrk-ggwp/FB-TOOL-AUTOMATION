import { SelectorMissingError, type AutomationResult } from '@fb/shared';
import { engagementSelectors } from '../selectors/engagement.selectors.js';
import { step, throwIfCancelled, type ActionContext } from './types.js';

export interface CommentInput {
  postUrl: string;
  text: string;
}

/**
 * Leaves a comment on a post. The comment box submits on Enter, which is both
 * what a person does and more reliable than hunting for the button, whose
 * accessible name changes between surfaces.
 */
export const comment = async (
  context: ActionContext,
  input: CommentInput,
): Promise<AutomationResult> => {
  const { page, navigation, automation } = context;
  const startedAt = Date.now();

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 25, 'Opening the post');
  await navigation.goto(page, input.postUrl);
  await navigation.settle(page);

  throwIfCancelled(context);

  step(context, 50, 'Finding the comment box');
  const box = page
    .getByRole(engagementSelectors.commentBox.role, { name: engagementSelectors.commentBox.name })
    .first();

  if (!(await box.isVisible({ timeout: automation.timeoutMs }).catch(() => false))) {
    throw new SelectorMissingError('comment box', input.postUrl);
  }

  await box.click();
  await box.pressSequentially(input.text, { delay: 12 });
  await navigation.pause();

  throwIfCancelled(context);
  step(context, 80, 'Sending the comment');
  await box.press('Enter');

  // The box emptying is the page's own confirmation that the comment went in.
  const deadline = Date.now() + automation.timeoutMs;
  while (Date.now() < deadline) {
    const remaining = (await box.textContent().catch(() => '')) ?? '';
    if (remaining.trim() === '') break;
    await navigation.pause();
  }

  await navigation.settle(page);

  return {
    resourceUrl: input.postUrl,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { characters: input.text.length },
  };
};
