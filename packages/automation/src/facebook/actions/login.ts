import {
  AccountGatedError,
  LoginFailedError,
  SelectorMissingError,
  sleep,
  type AutomationResult,
  type LoginStatus,
} from '@fb/shared';
import type { AccountCredentials } from '@fb/domain';
import {
  authenticationSelectors,
  FACEBOOK_LOGIN_URL,
} from '../selectors/authentication.selectors.js';
import { navigationSelectors } from '../selectors/navigation.selectors.js';
import { clickLike, humanType, settle } from '../humanInput.js';
import { generateTotp } from '../../totp/totp.js';
import { readMyProfile } from './profile.js';
import { firstVisible, step, throwIfCancelled, type ActionContext } from './types.js';

export interface LoginInput {
  credentials: AccountCredentials;
  waitForOperator: boolean;
}

/** Recorded on the account whatever the outcome, so the roster stays honest. */
export interface LoginVerdict {
  loginStatus: LoginStatus;
  loginReason: string | null;
  facebookName?: string | null;
  profileUrl?: string | null;
}

const GATE_KEYWORDS = [
  'checkpoint',
  'twofactor',
  'two_step_verification',
  'approvals',
  'confirmemail',
];

/**
 * Signs in with the stored username and password, typed the way a person
 * types them. Anything Facebook puts in the way — a captcha, a code, a
 * checkpoint — is handed to the operator through the open window and the
 * job waits for them, when waiting is allowed.
 */
export const login = async (
  context: ActionContext,
  input: LoginInput,
): Promise<AutomationResult> => {
  const startedAt = Date.now();
  const { page, navigation, session, automation } = context;
  const { username, password } = input.credentials;

  if (username === null || password === null || username === '' || password === '') {
    throw new LoginFailedError('no username and password are stored for this account');
  }

  step(context, 5, 'Checking whether a session already exists');
  await navigation.goto(page, navigationSelectors.home);
  if (await session.isLoggedIn(page, 5_000)) {
    const me = await readMyProfile(context);
    return verdictResult(startedAt, {
      loginStatus: 'logged_in',
      loginReason: 'already signed in',
      facebookName: me.name,
      profileUrl: me.url,
    });
  }

  step(context, 15, 'Opening the login page');
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      await page.goto(FACEBOOK_LOGIN_URL, { waitUntil: 'load', timeout: automation.timeoutMs });
      break;
    } catch (error) {
      if (attempt === 1)
        throw new LoginFailedError(`could not load the login page: ${String(error)}`, true);
      await sleep(3_000);
    }
  }
  await settle(page);
  await dismissAccountChooser(context);

  throwIfCancelled(context);
  step(context, 30, 'Typing the username');
  const email = await firstVisible([page.locator(authenticationSelectors.emailField)], 8_000);
  if (email === null) throw new SelectorMissingError('email field', page.url());
  await humanType(page, email, username);
  await sleep(300 + Math.random() * 500);

  step(context, 40, 'Typing the password');
  const pass = await firstVisible([page.locator(authenticationSelectors.passwordField)], 5_000);
  if (pass === null) throw new SelectorMissingError('password field', page.url());
  await humanType(page, pass, password);
  await sleep(400 + Math.random() * 700);

  step(context, 50, 'Submitting');
  const button = await firstVisible(
    [
      page.locator(authenticationSelectors.loginButton),
      page.getByRole('button', { name: authenticationSelectors.loginButtonRole.name }),
    ],
    8_000,
  );
  if (button === null) await page.keyboard.press('Enter');
  else await clickLike(page, button);
  await sleep(3_000 + Math.random() * 2_000);

  // A captcha can come up on the form or right after submitting. Unanswered,
  // it leaves the page sitting on the login screen, which used to be
  // reported as a wrong password.
  step(context, 60, 'Checking for a captcha');
  const captcha = await session.handleCaptcha(page);
  if (captcha === 'needs_human') {
    if (!input.waitForOperator) {
      return verdictResult(startedAt, {
        loginStatus: 'captcha',
        loginReason: 'captcha needs a person',
      });
    }
    await automation.askOperator({
      kind: 'captcha',
      message: 'Facebook is showing a captcha. Solve it in the browser window, then confirm here.',
    });
    if (!(await session.isLoggedIn(page, 5_000))) {
      await page.keyboard.press('Enter').catch(() => undefined);
      await sleep(3_000 + Math.random() * 2_000);
    }
  } else if (captcha === 'solved' && !(await session.isLoggedIn(page, 5_000))) {
    // The captcha was the gate on the form: submitting again is what logs in.
    await page.keyboard.press('Enter').catch(() => undefined);
    await sleep(3_000 + Math.random() * 2_000);
  }

  throwIfCancelled(context);
  step(context, 75, 'Checking for a checkpoint or code prompt');
  const gate = gateOf(page.url());
  if (gate !== null) {
    // A two-factor prompt with a stored authenticator secret is answered here,
    // from the secret, without a person or a phone. Anything else — a
    // checkpoint, an email confirmation, or 2FA with no secret — still needs
    // the operator or fails, exactly as before.
    if (gate.status === 'two_factor' && input.credentials.totpSecret !== null) {
      step(context, 80, 'Entering the authenticator code');
      if (await enterTotp(context, input.credentials.totpSecret)) {
        if (await session.isLoggedIn(page, 10_000)) {
          const me = await readMyProfile(context);
          return verdictResult(startedAt, {
            loginStatus: 'logged_in',
            loginReason: 'signed in with a two-factor code',
            facebookName: me.name,
            profileUrl: me.url,
          });
        }
      }
      // The code did not clear it: fall through to the operator or the verdict.
    }
    if (!input.waitForOperator) {
      // A gate URL can clear itself within seconds; judging the first frame
      // reported working accounts as gated.
      for (let i = 0; i < 20; i += 1) {
        await sleep(1_000);
        const url = page.url().toLowerCase();
        if (gateOf(url) !== null || url.includes('login')) continue;
        if (url.includes('facebook.com') && (await session.isLoggedIn(page, 3_000))) break;
      }
      if (!(await session.isLoggedIn(page, 2_000))) {
        return verdictResult(startedAt, {
          loginStatus: gate.status,
          loginReason: `${gate.reason}; finish it in the window`,
        });
      }
    } else {
      await automation.askOperator({
        kind: gate.status === 'two_factor' ? 'two_factor' : 'checkpoint',
        message: `${gate.reason}. Finish it in the browser window, then confirm here.`,
      });
      if (!(await session.isLoggedIn(page, 10_000))) {
        throw new AccountGatedError(gate.status, `${gate.reason} and it is still in the way`);
      }
    }
  }

  step(context, 90, 'Confirming the session');
  if (await session.isLoggedIn(page, 15_000)) {
    const me = await readMyProfile(context);
    return verdictResult(startedAt, {
      loginStatus: 'logged_in',
      loginReason: gate === null ? 'signed in' : `signed in after ${gate.reason}`,
      facebookName: me.name,
      profileUrl: me.url,
    });
  }

  const error = await firstVisible([page.locator(authenticationSelectors.loginError)], 3_000);
  if (error !== null) {
    const text = ((await error.innerText().catch(() => '')) || '').trim().slice(0, 120);
    throw new LoginFailedError(text || 'Facebook rejected the login');
  }

  const where = page.url().toLowerCase();
  if (where.includes('login')) {
    throw new LoginFailedError(
      'still on the login form: wrong password, or Facebook rejected the attempt',
    );
  }
  if (!where.includes('facebook.com')) {
    throw new LoginFailedError(`left Facebook for ${where.slice(0, 80)}`);
  }
  throw new LoginFailedError('the page ended somewhere that is not a signed-in Facebook');
};

/**
 * Types the current authenticator code into the two-factor field and submits.
 * Two codes are tried across a fresh 30-second window, since the first can
 * land in the last second of a step; false means neither was accepted or the
 * field never appeared, and the caller falls back.
 */
const enterTotp = async (context: ActionContext, secret: string): Promise<boolean> => {
  const { page } = context;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const field = await firstVisible(
      [page.locator(authenticationSelectors.twoFactorCodeField)],
      8_000,
    );
    if (field === null) return false;

    const code = generateTotp(secret);
    await field.fill('');
    await humanType(page, field, code);
    await sleep(400 + Math.random() * 500);

    const button = await firstVisible(
      [page.getByRole('button', authenticationSelectors.twoFactorContinue)],
      4_000,
    );
    if (button === null) await page.keyboard.press('Enter');
    else await clickLike(page, button);
    await sleep(4_000 + Math.random() * 2_000);

    if (await context.session.isLoggedIn(page, 6_000)) return true;
    // Still on the code page: a wrong or stale code. Wait out the step and
    // try once more with a freshly generated one.
    if (attempt === 0) {
      context.log('The first authenticator code was not accepted; trying the next window');
      await sleep(Math.max(0, 30_000 - (Math.floor(Date.now() / 1000) % 30) * 1_000));
    }
  }
  return false;
};

/**
 * Click past the "Continue as <name> / Use another profile" screen a
 * remembered-but-invalidated session lands on. It has no email field at all.
 */
const dismissAccountChooser = async (context: ActionContext): Promise<void> => {
  const link = context.page.getByText(authenticationSelectors.useAnotherProfile).first();
  try {
    if ((await link.count()) === 0) return;
    await link.click({ timeout: 8_000 });
    await sleep(3_000);
    context.log('Account chooser dismissed; the login form is open');
  } catch {
    // Not the chooser page.
  }
};

const gateOf = (url: string): { status: LoginStatus; reason: string } | null => {
  const lower = url.toLowerCase();
  if (!GATE_KEYWORDS.some((keyword) => lower.includes(keyword))) return null;
  if (
    lower.includes('two_step_verification') ||
    lower.includes('twofactor') ||
    lower.includes('approvals')
  ) {
    return { status: 'two_factor', reason: 'two-factor authentication required' };
  }
  if (lower.includes('confirmemail')) {
    return { status: 'email_confirmation', reason: 'email confirmation required' };
  }
  return { status: 'checkpoint', reason: 'checkpoint required' };
};

const verdictResult = (startedAt: number, verdict: LoginVerdict): AutomationResult => ({
  resourceUrl: verdict.profileUrl ?? null,
  durationMs: Date.now() - startedAt,
  screenshotPath: null,
  details: { ...verdict },
});

/** Where the session stands right now, with no typing at all. */
export const checkLogin = async (context: ActionContext): Promise<AutomationResult> => {
  const startedAt = Date.now();
  const { page, navigation, session } = context;

  step(context, 20, 'Opening Facebook');
  await navigation.goto(page, navigationSelectors.home);
  await sleep(2_000);

  step(context, 60, 'Reading the session');
  const verdict = await session.classify(page);
  if (verdict.status !== 'logged_in') {
    return verdictResult(startedAt, { loginStatus: verdict.status, loginReason: verdict.reason });
  }

  step(context, 85, 'Reading the profile name');
  const me = await readMyProfile(context);
  return verdictResult(startedAt, {
    loginStatus: 'logged_in',
    loginReason: null,
    facebookName: me.name,
    profileUrl: me.url,
  });
};
