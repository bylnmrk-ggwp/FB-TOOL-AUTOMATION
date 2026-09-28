export const GROUPS_FEED_URL = 'https://www.facebook.com/groups/?feed_type=group_post';

export const groupSelectors = {
  groupLink: 'a[href*="/groups/"]',
  /** Navigation entries that are not groups but match the link pattern. */
  ignoredNames: ['groups', 'see all groups', 'discover', 'your groups'] as const,

  alreadyMember: { role: 'button', name: /^joined$|^member$/i },
  joinButton: { role: 'button', name: /^join group$|^join$/i },
  answerQuestions: { role: 'button', name: /^answer/i },
  confirmJoin: { role: 'button', name: /^join$|^submit$|^confirm$/i },
  joinOutcome: { role: 'button', name: /^joined$|^pending$|^requested$|^cancel request$/i },
} as const;
