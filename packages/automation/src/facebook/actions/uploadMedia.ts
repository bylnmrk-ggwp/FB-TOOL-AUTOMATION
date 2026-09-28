import { SelectorMissingError, type AutomationResult, type MediaRef } from '@fb/shared';
import { composerSelectors } from '../selectors/composer.selectors.js';
import { navigationSelectors } from '../selectors/navigation.selectors.js';
import { step, throwIfCancelled, type ActionContext } from './types.js';

export interface UploadMediaInput {
  targetUrl: string;
  media: MediaRef[];
  caption?: string;
}

/**
 * Posts media to a specific surface — a page, a group, an album — rather than
 * the account's own feed. The composer on those pages is the same modal, which
 * is why this shares the composer selectors.
 */
export const uploadMedia = async (
  context: ActionContext,
  input: UploadMediaInput,
): Promise<AutomationResult> => {
  const { page, navigation, files, automation } = context;
  const startedAt = Date.now();

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 20, 'Opening the destination');
  await navigation.goto(page, input.targetUrl);
  await navigation.settle(page);

  throwIfCancelled(context);

  step(context, 35, 'Opening the composer');
  const opener = page
    .getByRole(composerSelectors.openComposer.role, { name: composerSelectors.openComposer.name })
    .first();

  if (!(await opener.isVisible({ timeout: automation.timeoutMs }).catch(() => false))) {
    throw new SelectorMissingError('post composer', input.targetUrl);
  }
  await opener.click();

  const dialog = page.getByRole(navigationSelectors.dialog.role).first();
  await dialog.waitFor({ state: 'visible', timeout: automation.timeoutMs });
  await navigation.pause();

  step(context, 55, `Attaching ${input.media.length} file(s)`);
  const paths = await Promise.all(input.media.map((media) => files.resolvePath(media.id)));

  // The Photo/Video tab has to be open before the hidden input exists on some
  // surfaces; clicking it is harmless when it is already open.
  const addPhoto = dialog
    .getByRole(composerSelectors.addPhotoButton.role, {
      name: composerSelectors.addPhotoButton.name,
    })
    .first();
  if (await addPhoto.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await addPhoto.click();
    await navigation.pause();
  }

  await dialog.locator(composerSelectors.fileInput).first().setInputFiles(paths);
  await navigation.pause();

  if (input.caption !== undefined && input.caption.length > 0) {
    throwIfCancelled(context);
    step(context, 70, 'Writing the caption');
    const body = dialog
      .getByRole(composerSelectors.postBody.role, { name: composerSelectors.postBody.name })
      .first();
    await body.click();
    await body.pressSequentially(input.caption, { delay: 12 });
    await navigation.pause();
  }

  throwIfCancelled(context);
  step(context, 85, 'Publishing');
  await dialog
    .getByRole(composerSelectors.submit.role, { name: composerSelectors.submit.name })
    .first()
    .click({ timeout: automation.timeoutMs });

  await dialog.waitFor({ state: 'hidden', timeout: automation.timeoutMs });
  await navigation.settle(page);

  return {
    resourceUrl: input.targetUrl,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { attachments: input.media.length, captioned: input.caption !== undefined },
  };
};
