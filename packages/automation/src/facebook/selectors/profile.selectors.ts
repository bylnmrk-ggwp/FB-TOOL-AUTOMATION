export const PROFILE_URLS = {
  me: 'https://www.facebook.com/me',
  about: 'https://www.facebook.com/me/about',
  aboutBio: 'https://www.facebook.com/me/about?section=bio',
} as const;

export const profileSelectors = {
  /** Its presence means the profile has no picture yet. */
  addPhotoTexts: ['add profile picture', 'add photo'] as const,
  choosePicture: { role: 'button', name: /choose profile picture|update profile picture/i },
  fileInput: 'input[type="file"]',
  save: { role: 'button', name: /^save$|^done$/i },

  bioInput:
    'div[role="textbox"][aria-label*="bio" i], div[role="textbox"][aria-label*="about" i], textarea[aria-label*="bio" i], input[aria-label*="bio" i]',
  editIntro: { role: 'button', name: /edit details|edit intro|edit bio|add bio/i },
  anyTextbox: 'div[role="textbox"][contenteditable="true"], textarea, input[type="text"]',

  /** Facebook UI strings that must never be mistaken for a person's name. */
  notNames: [
    'facebook',
    'home',
    'watch',
    'marketplace',
    'groups',
    'gaming',
    'menu',
    'notifications',
    'messages',
    'profile',
    'settings',
    'log out',
    'create',
    'edit',
    'add',
    'photo',
    'share a thought',
    "what's on your mind",
    'write something',
    'say something',
    'post',
    'share',
    'update status',
  ] as const,
} as const;
