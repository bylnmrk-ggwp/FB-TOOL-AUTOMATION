export const messagingSelectors = {
  /** The message field in an open Messenger thread. */
  messageBox: { role: 'textbox', name: /message|aa/i },
  sendButton: { role: 'button', name: /^send$|press enter to send/i },

  /** Attachment input inside a thread. */
  fileInput: 'input[type="file"]',

  /** The last message bubble, used to confirm the send landed. */
  lastMessage: '[role="row"]:last-of-type, [data-testid="message-container"]:last-of-type',

  /** Facebook shows this when the recipient cannot be messaged. */
  blockedNotice: { role: 'heading', name: /can't reply|not available|unavailable/i },
} as const;
