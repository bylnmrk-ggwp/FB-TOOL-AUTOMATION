import { SelectorMissingError, type AutomationResult, type MediaRef } from '@fb/shared';
import { composerSelectors } from '../selectors/composer.selectors.js';
import { navigationSelectors } from '../selectors/navigation.selectors.js';
import { step, throwIfCancelled, type ActionContext } from './types.js';

export interface CreatePostInput {
  text: string;
  media: MediaRef[];
  audience: 'public' | 'friends' | 'only_me';
}

/**
 * Writes a post on the account's own feed.
 *
 * The composer is a modal, so every step scopes itself to that dialog rather
 * than to the page: the feed underneath has buttons with the same names.
 */
export const createPost = async (
  context: ActionContext,
  input: CreatePostInput,
): Promise<AutomationResult> => {
  const { page, navigation, files, automation } = context;
  const startedAt = Date.now();

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 15, 'Opening the composer');
  const opener = page
    .getByRole(composerSelectors.openComposer.role, { name: composerSelectors.openComposer.name })
    .first();

  if (!(await opener.isVisible().catch(() => false))) {
    throw new SelectorMissingError('post composer', page.url());
  }
  await opener.click();
  await navigation.pause();

  const dialog = page.getByRole(navigationSelectors.dialog.role).first();
  await dialog.waitFor({ state: 'visible', timeout: automation.timeoutMs });

  throwIfCancelled(context);

  step(context, 30, 'Typing the post');
  const body = dialog
    .getByRole(composerSelectors.postBody.role, { name: composerSelectors.postBody.name })
    .first();
  await body.click();
  // Typed rather than filled: a contenteditable that is filled programmatically
  // often leaves the Post button disabled.
  await body.pressSequentially(input.text, { delay: 12 });
  await navigation.pause();

  if (input.audience !== 'friends') {
    step(context, 45, `Setting the audience to ${input.audience}`);
    await setAudience(context, input.audience);
  }

  if (input.media.length > 0) {
    throwIfCancelled(context);
    step(context, 60, `Attaching ${input.media.length} file(s)`);

    const paths = await Promise.all(input.media.map((media) => files.resolvePath(media.id)));
    const fileInput = dialog.locator(composerSelectors.fileInput).first();
    await fileInput.setInputFiles(paths);
    await navigation.pause();
  }

  throwIfCancelled(context);
  step(context, 80, 'Publishing');

  const submit = dialog
    .getByRole(composerSelectors.submit.role, { name: composerSelectors.submit.name })
    .first();
  await submit.click({ timeout: automation.timeoutMs });

  // The dialog closing is what confirms the post went in; a stuck dialog means
  // Facebook refused it.
  await dialog.waitFor({ state: 'hidden', timeout: automation.timeoutMs });
  await navigation.settle(page);

  step(context, 95, 'Reading back the permalink');
  const resourceUrl = await latestPostUrl(context);

  return {
    resourceUrl,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { characters: input.text.length, attachments: input.media.length },
  };
};

const setAudience = async (
  context: ActionContext,
  audience: 'public' | 'friends' | 'only_me',
): Promise<void> => {
  const { page, navigation, automation } = context;
  const dialog = page.getByRole(navigationSelectors.dialog.role).first();

  const audienceButton = dialog
    .getByRole(composerSelectors.audienceButton.role, {
      name: composerSelectors.audienceButton.name,
    })
    .first();

  if (!(await audienceButton.isVisible().catch(() => false))) return;

  await audienceButton.click();
  await navigation.pause();

  const option = composerSelectors.audienceOption[audience];
  await page
    .getByRole(option.role, { name: option.name })
    .first()
    .click({ timeout: automation.timeoutMs });

  await page
    .getByRole(composerSelectors.audienceConfirm.role, {
      name: composerSelectors.audienceConfirm.name,
    })
    .first()
    .click({ timeout: automation.timeoutMs })
    .catch(() => undefined);

  await navigation.pause();
};

/**
 * Best effort: the permalink is useful but not worth failing a published post
 * over, so a missing link returns null rather than throwing.
 */
const latestPostUrl = async (context: ActionContext): Promise<string | null> => {
  try {
    const link = context.page.locator(composerSelectors.latestPostLink).first();
    if (!(await link.isVisible({ timeout: 3_000 }))) return null;
    return await link.getAttribute('href');
  } catch {
    return null;
  }
};
