export const FRIEND_URLS = {
  suggestions: 'https://www.facebook.com/friends/suggestions/',
  requests: 'https://www.facebook.com/friends/requests/',
  requestsReceived: 'https://www.facebook.com/friends/requests/?type=received',
  myFriends: 'https://www.facebook.com/me/friends',
} as const;

export const friendSelectors = {
  addFriend: 'Add Friend',
  seeMore: { role: 'button', name: /^see more$/i },

  /** Words on a Confirm/Accept button, and the words that rule one out. */
  confirmWords: ['confirm', 'accept'] as const,
  confirmExcludes: ['menu', 'back', 'close', 'search', 'delete', 'decline', 'ignore'] as const,

  friendsCount: /([\d,]+)\s*friends?/i,
} as const;
