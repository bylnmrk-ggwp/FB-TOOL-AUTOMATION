/**
 * Everything that tells a signed-in page from a signed-out one.
 *
 * Selectors live here rather than beside the code that uses them because the
 * markup belongs to somebody else: when it changes, the fix should be one file,
 * not a search through the actions.
 */
export const authenticationSelectors = {
  /** The login form only exists when the session is gone. */
  emailField: 'input[name="email"]',
  passwordField: 'input[name="pass"]',
  loginButton: '[data-testid="royal_login_button"], button[name="login"]',

  /** Present on every signed-in page. */
  accountMenu: { role: 'button', name: /your profile|account|account controls/i },
  navigationBar: '[role="banner"], [role="navigation"]',

  /** Shown when Facebook wants a checkpoint or a code before letting us in. */
  checkpointHeading: { role: 'heading', name: /we need to confirm|checkpoint|suspicious/i },
  twoFactorPrompt: { role: 'heading', name: /two-factor|enter (login|security) code/i },
} as const;
