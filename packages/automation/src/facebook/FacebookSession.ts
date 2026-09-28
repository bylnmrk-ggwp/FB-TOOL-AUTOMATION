import type { Frame, Page } from 'playwright';
import { AccountGatedError, NotLoggedInError, sleep, type LoginStatus } from '@fb/shared';
import {
  ARKOSE_HOSTS,
  authenticationSelectors,
  CAPTCHA_TEXTS,
  CHECKPOINT_TEXTS,
  DISABLED_TEXTS,
  GATE_PATHS,
  LOGIN_GATE_SCRIPT,
} from './selectors/authentication.selectors.js';
import { navigationSelectors } from './selectors/navigation.selectors.js';
import type { FacebookNavigation } from './FacebookNavigation.js';

/** What a page says about the account behind it. */
export interface AccessVerdict {
  status: LoginStatus;
  reason: string | null;
}

/**
 * Whether this profile is usable right now, and if not, why.
 *
 * The system never types a password on its own initiative: a person signs in
 * once (or the login action does, with stored credentials), and the profile
 * keeps the session. So every other action starts here with a read-only
 * check — a job that ran against a signed-out profile would otherwise fail
 * somewhere deep in the composer with a confusing message.
 */
export class FacebookSession {
  constructor(private readonly navigation: FacebookNavigation) {}

  /** True when the path is one of Facebook's account gates. */
  isGatedUrl(url: string): boolean {
    let path: string;
    try {
      path = new URL(url).pathname.toLowerCase();
    } catch {
      return false;
    }
    return GATE_PATHS.some((prefix) => path.startsWith(prefix));
  }

  /** The home page itself, query string ignored: the one place a usable session lands. */
  isHomeUrl(url: string): boolean {
    try {
      const parsed = new URL(url);
      const host = parsed.hostname.toLowerCase();
      if (host !== 'facebook.com' && !host.endsWith('.facebook.com')) return false;
      const path = parsed.pathname.replace(/\/+$/, '');
      return path === '' || path === '/home.php';
    } catch {
      return false;
    }
  }

  async loginOverlayPresent(page: Page): Promise<boolean> {
    try {
      return Boolean(await page.evaluate(LOGIN_GATE_SCRIPT));
    } catch {
      return false;
    }
  }

  /** Polls for up to `timeoutMs`: a page mid-redirect must not be judged on its first frame. */
  async isLoggedIn(page: Page, timeoutMs = 10_000): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const url = page.url().toLowerCase();
      if (!url.includes('facebook.com')) {
        await sleep(500);
        continue;
      }

      const onForm =
        (await page.locator(authenticationSelectors.emailField).count()) > 0 ||
        (await page.locator(authenticationSelectors.passwordField).count()) > 0;

      if (this.isGatedUrl(url) || onForm || (await this.loginOverlayPresent(page))) {
        await sleep(500);
        continue;
      }
      return true;
    }
    return false;
  }

  /**
   * Why Facebook access is unavailable — or `logged_in` when it is not.
   * A live session is checked first, so an account that failed for some
   * other reason is never recorded as signed out.
   */
  async classify(page: Page): Promise<AccessVerdict> {
    const url = page.url().toLowerCase();

    if (url.includes('facebook.com') && (await this.isLoggedIn(page, 5_000))) {
      return { status: 'logged_in', reason: null };
    }
    if (!url.includes('facebook.com')) {
      return {
        status: 'unknown',
        reason: `left Facebook for ${url.slice(0, 80) || 'a blank page'}`,
      };
    }

    const body = (
      await page
        .locator('body')
        .innerText({ timeout: 3_000 })
        .catch(() => '')
    ).toLowerCase();

    if (DISABLED_TEXTS.some((text) => body.includes(text))) {
      return { status: 'disabled', reason: 'Facebook says the account is disabled or suspended' };
    }
    if (url.includes('confirmemail')) {
      return { status: 'email_confirmation', reason: 'email confirmation required' };
    }
    if (
      url.includes('two_step_verification') ||
      url.includes('twofactor') ||
      url.includes('approvals')
    ) {
      return { status: 'two_factor', reason: 'two-factor authentication required' };
    }
    if (url.includes('checkpoint') || CHECKPOINT_TEXTS.some((text) => body.includes(text))) {
      return { status: 'checkpoint', reason: 'checkpoint or identity confirmation required' };
    }
    if (await this.captchaPresent(page)) {
      return { status: 'captcha', reason: 'a captcha is in the way' };
    }
    if (url.includes('login') || (await this.loginOverlayPresent(page))) {
      return { status: 'logged_out', reason: 'logged out or the session expired' };
    }
    return { status: 'logged_out', reason: 'not logged in (unknown gate)' };
  }

  /** Throws unless the profile is signed in and not sitting on a gate. */
  async assertUsable(page: Page, accountId: string): Promise<void> {
    await this.navigation.goto(page, navigationSelectors.home);
    const verdict = await this.classify(page);
    if (verdict.status === 'logged_in') return;
    if (verdict.status === 'logged_out') throw new NotLoggedInError(accountId);
    throw new AccountGatedError(
      verdict.status,
      `Facebook is holding this account at a gate: ${verdict.reason ?? verdict.status}. Open the browser and resolve it.`,
    );
  }

  // --- Captchas -------------------------------------------------------------

  /** The reCAPTCHA checkbox frame, or null. Only the anchor can be clicked. */
  recaptchaFrame(page: Page): Frame | null {
    return (
      page
        .frames()
        .find((frame) => frame.url().includes('recaptcha') && frame.url().includes('anchor')) ??
      null
    );
  }

  async recaptchaChallengeOpen(page: Page): Promise<boolean> {
    return page
      .frames()
      .some((frame) => frame.url().includes('recaptcha') && frame.url().includes('bframe'));
  }

  async recaptchaSolved(page: Page): Promise<boolean> {
    try {
      const length = await page.evaluate((selector) => {
        const element = document.querySelector<HTMLTextAreaElement>(selector);
        return element === null ? 0 : element.value.length;
      }, authenticationSelectors.recaptchaToken);
      return length > 0;
    } catch {
      return false;
    }
  }

  /** Facebook's own picture challenge, which only a person can answer. */
  async arkosePresent(page: Page): Promise<boolean> {
    if (page.frames().some((frame) => ARKOSE_HOSTS.some((host) => frame.url().includes(host)))) {
      return true;
    }
    const body = (
      await page
        .locator('body')
        .innerText({ timeout: 3_000 })
        .catch(() => '')
    ).toLowerCase();
    return CAPTCHA_TEXTS.some((text) => body.includes(text));
  }

  async captchaPresent(page: Page): Promise<boolean> {
    return this.recaptchaFrame(page) !== null || (await this.arkosePresent(page));
  }

  /**
   * Deals with an "I'm not a robot" box. The checkbox itself is ticked here:
   * on a profile with history reCAPTCHA usually issues its token from that
   * alone. A picture challenge is handed to a person through `askOperator`.
   *
   * Returns `none`, `solved` or `needs_human`.
   */
  async handleCaptcha(page: Page): Promise<'none' | 'solved' | 'needs_human'> {
    const frame = this.recaptchaFrame(page);
    if (frame === null) return (await this.arkosePresent(page)) ? 'needs_human' : 'none';
    if (await this.recaptchaSolved(page)) return 'solved';

    try {
      await frame.locator(authenticationSelectors.recaptchaAnchor).click({ timeout: 10_000 });
    } catch {
      // The token check below decides.
    }

    for (let i = 0; i < 10; i += 1) {
      await sleep(1_000);
      if (await this.recaptchaSolved(page)) return 'solved';
      if (await this.recaptchaChallengeOpen(page)) break;
    }
    return 'needs_human';
  }
}
