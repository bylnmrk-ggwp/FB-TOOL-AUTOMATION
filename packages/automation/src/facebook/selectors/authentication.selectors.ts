/**
 * Everything that tells a signed-in page from a signed-out one.
 *
 * Selectors live here rather than beside the code that uses them because the
 * markup belongs to somebody else: when it changes, the fix should be one file,
 * not a search through the actions.
 */
export const FACEBOOK_LOGIN_URL = 'https://www.facebook.com/login.php';

export const authenticationSelectors = {
  /** The login form only exists when the session is gone. */
  emailField: 'input[name="email"], input#email, input[type="email"]',
  passwordField: 'input[name="pass"], input#pass, input[type="password"]',
  loginButton: 'button[name="login"], button[type="submit"], input[type="submit"]',
  loginButtonRole: { role: 'button', name: /^log in$/i },

  /** A remembered-but-invalidated session lands on a chooser with no form. */
  useAnotherProfile: /^use another profile$/i,

  /** Present on every signed-in page. */
  accountMenu: { role: 'button', name: /your profile|account|account controls/i },

  /** Shown when Facebook wants a checkpoint or a code before letting us in. */
  checkpointHeading: { role: 'heading', name: /we need to confirm|checkpoint|suspicious/i },
  twoFactorPrompt: { role: 'heading', name: /two-factor|enter (login|security) code/i },
  /** The 6-digit login-code field on the two-factor page. */
  twoFactorCodeField:
    'input[name="approvals_code"], input[autocomplete="one-time-code"], input[name="code"], input[type="tel"][maxlength="6"], input[aria-label*="code" i]',
  twoFactorContinue: { role: 'button', name: /continue|submit|next|confirm/i },

  /** The reCAPTCHA checkbox lives in the anchor frame; the puzzle in bframe. */
  recaptchaAnchor: '#recaptcha-anchor',
  recaptchaToken: '#g-recaptcha-response, textarea[name="g-recaptcha-response"]',
  loginError: '[role="alert"], #error_box, .uiError',
} as const;

/**
 * Path prefixes Facebook sends a session it will not let use the account: a
 * login form, a checkpoint, a two-factor prompt, an email confirmation or an
 * account-recovery flow. The PATH decides, never a substring of the whole URL,
 * or a group called "carrecovery" would read as a recovery gate.
 */
export const GATE_PATHS = [
  '/login',
  '/checkpoint',
  '/twofactor',
  '/two_step_verification',
  '/approvals',
  '/confirmemail',
  '/recover',
] as const;

export const ARKOSE_HOSTS = ['arkoselabs.com', 'funcaptcha.co', 'arkoselabs.cn'] as const;

export const CAPTCHA_TEXTS = [
  "confirm you're human",
  "confirm that you're human",
  'confirm you are human',
  'security check',
  'enter the characters',
  'solve this puzzle',
  "let's confirm you're human",
  "i'm not a robot",
] as const;

export const DISABLED_TEXTS = [
  'account has been disabled',
  'account is disabled',
  'we suspended your account',
  'your account was suspended',
  'account suspended',
  'you cannot use facebook',
] as const;

export const CHECKPOINT_TEXTS = [
  'confirm your identity',
  'security check',
  'checkpoint',
  'review requested',
  'request a review',
  'two-factor',
  'enter the code',
  'account restricted',
] as const;

/**
 * Runs inside the page: is a login gate showing? The "See more on Facebook"
 * overlay, a visible login form, or the account chooser a server-invalidated
 * session lands on. One owner for that question.
 */
export const LOGIN_GATE_SCRIPT = `() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  for (const d of document.querySelectorAll('[role="dialog"]')) {
    if (!vis(d)) continue;
    if ((d.innerText || '').toLowerCase().includes('see more on facebook')) return true;
  }
  for (const i of document.querySelectorAll('input')) {
    if (!vis(i)) continue;
    const name = (i.name || '').toLowerCase();
    const type = (i.type || '').toLowerCase();
    if (name === 'email' || name === 'pass' || type === 'email' || type === 'password') return true;
  }
  const body = (document.body ? document.body.innerText : '').toLowerCase();
  if (body.includes('use another profile')) return true;
  if (body.includes('log into another account')) return true;
  return false;
}`;
