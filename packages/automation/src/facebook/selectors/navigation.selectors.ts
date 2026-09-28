export const FACEBOOK_ORIGIN = 'https://www.facebook.com';

export const navigationSelectors = {
  home: `${FACEBOOK_ORIGIN}/`,
  messages: `${FACEBOOK_ORIGIN}/messages/t`,

  /** Cookie and notification banners that cover the page on a fresh profile. */
  cookieAccept: { role: 'button', name: /allow all cookies|accept all|only allow essential/i },
  notificationsDismiss: { role: 'button', name: /not now|block|don't allow/i },
  dialogClose: { role: 'button', name: /close|dismiss/i },

  /** A generic modal. Facebook puts the composer, the reaction bar and errors in one. */
  dialog: { role: 'dialog' },
} as const;
