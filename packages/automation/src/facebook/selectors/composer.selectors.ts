export const composerSelectors = {
  /** The collapsed box on the feed that opens the real composer. */
  openComposer: { role: 'button', name: /what's on your mind|what are you thinking/i },

  /** The editable area inside the open composer dialog. */
  postBody: { role: 'textbox', name: /what's on your mind|what are you thinking/i },

  /** Hidden until the photo/video tab is chosen, and never clicked directly. */
  fileInput: 'input[type="file"][accept*="image"], input[type="file"]',
  addPhotoButton: { role: 'button', name: /photo\/video|add photos|add photo/i },

  audienceButton: { role: 'button', name: /edit audience|privacy|public|friends|only me/i },
  audienceOption: {
    public: { role: 'radio', name: /^public$/i },
    friends: { role: 'radio', name: /^friends$/i },
    only_me: { role: 'radio', name: /^only me$/i },
  },
  audienceConfirm: { role: 'button', name: /^done$/i },

  submit: { role: 'button', name: /^post$/i },

  /** Appears while the post is being published and disappears when it is done. */
  posting: { role: 'progressbar' },

  /** The permalink of the newest post on our own timeline. */
  latestPostLink: 'a[href*="/posts/"], a[href*="story_fbid="], a[href*="/permalink/"]',
} as const;
