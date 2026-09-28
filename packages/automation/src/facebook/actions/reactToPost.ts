import { SelectorMissingError, type AutomationResult, type ReactionType } from '@fb/shared';
import { engagementSelectors } from '../selectors/engagement.selectors.js';
import { step, throwIfCancelled, type ActionContext } from './types.js';

export interface ReactInput {
  postUrl: string;
  reaction: ReactionType;
}

/**
 * Reacts to a post.
 *
 * A plain Like is a click. Anything else needs the reaction bar, which only
 * appears while the pointer rests on the Like button — so the hover is part of
 * the action, not an optimisation.
 */
export const reactToPost = async (
  context: ActionContext,
  input: ReactInput,
): Promise<AutomationResult> => {
  const { page, navigation, automation } = context;
  const startedAt = Date.now();

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 30, 'Opening the post');
  await navigation.goto(page, input.postUrl);
  await navigation.settle(page);

  throwIfCancelled(context);

  const likeButton = page
    .getByRole(engagementSelectors.likeButton.role, { name: engagementSelectors.likeButton.name })
    .first();

  if (!(await likeButton.isVisible({ timeout: automation.timeoutMs }).catch(() => false))) {
    throw new SelectorMissingError('like button', input.postUrl);
  }

  if (input.reaction === 'like') {
    step(context, 70, 'Liking the post');
    await likeButton.click();
  } else {
    step(context, 60, 'Opening the reaction bar');
    await likeButton.hover();
    await navigation.pause();

    const target = engagementSelectors.reaction(input.reaction);
    const reaction = page.getByRole(target.role, { name: target.name }).first();

    if (!(await reaction.isVisible({ timeout: 5_000 }).catch(() => false))) {
      throw new SelectorMissingError(`${input.reaction} reaction`, input.postUrl);
    }

    step(context, 80, `Reacting with ${input.reaction}`);
    await reaction.click();
  }

  await navigation.pause();

  return {
    resourceUrl: input.postUrl,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { reaction: input.reaction },
  };
};
