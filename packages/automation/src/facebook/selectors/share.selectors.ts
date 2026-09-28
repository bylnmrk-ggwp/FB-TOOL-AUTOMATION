/** The share sheet and the composer it can open. */
export const shareSelectors = {
  /** The post itself; the Share button is looked for inside it first. */
  article: '[role="article"]',

  shareButton: { role: 'button', name: /^share$|send this to friends or post it on your profile/i },

  /** Options on the share sheet, tried in order; the first that exists wins. */
  timelineOptions: ['Share now', 'Share to feed', 'Share to Feed'] as const,
  storyOptions: ['Your story', 'Your Story', 'Share to your story'] as const,
  groupOptions: ['Group', 'Share to a group', 'Share to a Group'] as const,
  /** Routes that open the full composer instead of posting in one click. */
  composerOptions: ['Share to Feed', 'Share to News Feed', 'Write Post', 'Share to feed'] as const,

  optionContainers: [
    '[role="dialog"] [role="menuitem"]',
    '[role="menu"] [role="menuitem"]',
    '[role="dialog"] [role="button"]',
    '[role="menu"] [role="button"]',
  ] as const,

  groupSearch:
    'input[placeholder*="search" i], input[role="combobox"], input[aria-label*="search" i]',
  groupResultContainers: ['a[href*="/groups/"]', '[role="option"]', '[role="menuitem"]'] as const,

  /**
   * The composer's Post button, in every language Facebook serves it. The
   * group flow and the composer retry both press this.
   */
  postLabels: [
    'post',
    'share',
    'done',
    'publish',
    'i-post',
    'mag-post',
    'publicar',
    'publier',
    'postar',
    'posten',
    'pubblica',
  ] as const,

  /** Words that mean the share sheet is still up after a share was attempted. */
  sheetStillOpenTexts: [
    'share now',
    'your story',
    'share to feed',
    'send this to',
    'write something about this',
  ] as const,

  /** Facebook's own "try again" family of refusals; worth one more attempt. */
  transientErrorTexts: [
    'something went wrong',
    'please try again',
    'try again later',
    'temporarily unavailable',
    "couldn't load",
    'could not load',
  ] as const,

  /** Facebook naming the account is a restriction, not a hiccup. */
  restrictionTexts: [
    'temporarily blocked',
    'restricted',
    "you're temporarily blocked",
    'feature temporarily blocked',
    'community standards',
    'limit',
  ] as const,

  ownPostMarkers: ['edit post', 'turn on notifications for this post', 'save post'] as const,
} as const;
