import type { Page } from 'playwright';
import { AutomationBlockedError, NotLoggedInError } from '@fb/shared';
import { authenticationSelectors } from './selectors/authentication.selectors.js';
import { navigationSelectors } from './selectors/navigation.selectors.js';
import type { FacebookNavigation } from './FacebookNavigation.js';

/**
 * Whether this profile is usable right now.
 *
 * The system never types a password: a person signs in once inside the
 * persistent profile, and the profile keeps the session. That makes this a
 * read-only check, and it is the first thing every action does — a job that
 * runs against a signed-out profile would otherwise fail somewhere deep in the
 * composer with a confusing message.
 */
export class FacebookSession {
  constructor(private readonly navigation: FacebookNavigation) {}

  async isLoggedIn(page: Page): Promise<boolean> {
    const loginForm = page.locator(authenticationSelectors.emailField).first();
    try {
      if (await loginForm.isVisible({ timeout: 2_000 })) return false;
    } catch {
      // Not visible, which is what we want.
    }
    return true;
  }

  /** Throws unless the profile is signed in and not sitting on a checkpoint. */
  async assertUsable(page: Page, accountId: string): Promise<void> {
    await this.navigation.goto(page, navigationSelectors.home);

    if (!(await this.isLoggedIn(page))) throw new NotLoggedInError(accountId);

    const checkpoint = page
      .getByRole(authenticationSelectors.checkpointHeading.role, {
        name: authenticationSelectors.checkpointHeading.name,
      })
      .first();

    try {
      if (await checkpoint.isVisible({ timeout: 1_500 })) {
        throw new AutomationBlockedError(
          'Facebook is asking this account to confirm its identity. Open the browser and resolve it.',
        );
      }
    } catch (error) {
      if (error instanceof AutomationBlockedError) throw error;
      // Not visible: nothing to resolve.
    }
  }
}
