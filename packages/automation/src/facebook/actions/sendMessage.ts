import {
  AutomationBlockedError,
  SelectorMissingError,
  type AutomationResult,
  type MediaRef,
} from '@fb/shared';
import { messagingSelectors } from '../selectors/messaging.selectors.js';
import { navigationSelectors } from '../selectors/navigation.selectors.js';
import { step, throwIfCancelled, type ActionContext } from './types.js';

export interface SendMessageInput {
  threadId: string;
  text: string;
  media: MediaRef[];
}

/**
 * Sends a Messenger message to one thread.
 *
 * The thread id is treated as a path segment and encoded: it arrives from the
 * API, and a raw value could otherwise navigate somewhere else entirely.
 */
export const sendMessage = async (
  context: ActionContext,
  input: SendMessageInput,
): Promise<AutomationResult> => {
  const { page, navigation, files, automation } = context;
  const startedAt = Date.now();

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  const threadUrl = `${navigationSelectors.messages}/${encodeURIComponent(input.threadId)}`;

  step(context, 25, 'Opening the conversation');
  await navigation.goto(page, threadUrl);
  await navigation.settle(page);

  const blocked = page
    .getByRole(messagingSelectors.blockedNotice.role, {
      name: messagingSelectors.blockedNotice.name,
    })
    .first();
  if (await blocked.isVisible({ timeout: 1_500 }).catch(() => false)) {
    throw new AutomationBlockedError('This conversation does not accept messages');
  }

  throwIfCancelled(context);

  const box = page
    .getByRole(messagingSelectors.messageBox.role, { name: messagingSelectors.messageBox.name })
    .first();

  if (!(await box.isVisible({ timeout: automation.timeoutMs }).catch(() => false))) {
    throw new SelectorMissingError('message box', threadUrl);
  }

  if (input.media.length > 0) {
    step(context, 45, `Attaching ${input.media.length} file(s)`);
    const paths = await Promise.all(input.media.map((media) => files.resolvePath(media.id)));
    await page.locator(messagingSelectors.fileInput).first().setInputFiles(paths);
    await navigation.pause();
  }

  step(context, 65, 'Typing the message');
  await box.click();
  await box.pressSequentially(input.text, { delay: 12 });
  await navigation.pause();

  throwIfCancelled(context);
  step(context, 85, 'Sending');
  await box.press('Enter');
  await navigation.settle(page);

  return {
    resourceUrl: threadUrl,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { characters: input.text.length, attachments: input.media.length },
  };
};
