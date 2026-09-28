export const engagementSelectors = {
  /** Comment box on a post page. */
  commentBox: { role: 'textbox', name: /write a comment|write a public comment/i },
  commentSubmit: { role: 'button', name: /^comment$|^post$/i },

  /** The Like button; hovering it opens the reaction bar. */
  likeButton: { role: 'button', name: /^like$|^react$/i },
  reactionBar: { role: 'toolbar', name: /reactions/i },
  reaction: (name: string) => ({ role: 'button' as const, name: new RegExp(`^${name}$`, 'i') }),

  /** Shown once a reaction has been applied. */
  reactedIndicator: { role: 'button', name: /remove (like|love|care|haha|wow|sad|angry)/i },
} as const;
