import { sleep, type AutomationResult, type MediaRef } from '@fb/shared';
import { PROFILE_URLS, profileSelectors } from '../selectors/profile.selectors.js';
import { clickLike } from '../humanInput.js';
import { acceptFriendRequests, addFriends, countFriends } from './friends.js';
import { firstVisible, step, throwIfCancelled, type ActionContext } from './types.js';

export interface MyProfile {
  url: string | null;
  name: string | null;
}

/** The account's own profile URL and display name, from /me. */
export const readMyProfile = async (context: ActionContext): Promise<MyProfile> => {
  const { page } = context;
  try {
    await page.goto(PROFILE_URLS.me, {
      waitUntil: 'domcontentloaded',
      timeout: context.automation.timeoutMs,
    });
    await sleep(3_000);
  } catch {
    return { url: null, name: null };
  }

  let url: string | null = page.url();
  if (url.includes('profile.php')) {
    const id = /[?&]id=(\d+)/.exec(url)?.[1] ?? (await userIdFromPage(context));
    url = id === null ? url : `https://www.facebook.com/profile.php?id=${id}`;
  } else {
    url = url.split('?')[0] ?? url;
  }

  const name = await page.evaluate(
    (notNames) => {
      const valid = (text: string | null | undefined): text is string => {
        if (!text || text.length < 2 || text.length > 50) return false;
        const lower = text.toLowerCase();
        if (notNames.some((bad) => lower === bad || lower.includes(bad))) return false;
        if (text === lower && text.length > 5) return false;
        return !text.endsWith('...') && !text.endsWith('…');
      };

      const og = document
        .querySelector<HTMLMetaElement>('meta[property="og:title"]')
        ?.content?.trim();
      if (valid(og)) return og;

      for (const heading of document.querySelectorAll('h1')) {
        const text = (heading.textContent || '').trim();
        if (valid(text) && !/\d/.test(text)) return text;
      }

      const title = document.title.replace(/[|-]\s*Facebook.*$/i, '').trim();
      return valid(title) ? title : null;
    },
    [...profileSelectors.notNames],
  );

  return { url, name };
};

const userIdFromPage = (context: ActionContext): Promise<string | null> =>
  context.page.evaluate(() => {
    for (const script of document.querySelectorAll('script')) {
      const text = script.textContent || '';
      const match =
        /"userID":"(\d+)"/.exec(text) ??
        /"USER_ID":"(\d+)"/.exec(text) ??
        /"ownerID":"(\d+)"/.exec(text);
      if (match !== null) return match[1] ?? null;
    }
    const link = document.querySelector<HTMLAnchorElement>('a[href*="profile.php?id="]');
    return link === null ? null : (/[?&]id=(\d+)/.exec(link.href)?.[1] ?? null);
  });

interface ProfileSetupState {
  hasProfilePicture: boolean;
}

/** Whether the profile has a picture: an "Add profile picture" button means no. */
const checkProfileSetup = async (context: ActionContext): Promise<ProfileSetupState> => {
  const { page } = context;
  await page.goto(PROFILE_URLS.me, {
    waitUntil: 'domcontentloaded',
    timeout: context.automation.timeoutMs,
  });
  await sleep(4_000);

  const hasAddButton = await page.evaluate(
    (texts) => {
      for (const element of document.querySelectorAll<HTMLElement>(
        '[role="button"], a, span, div',
      )) {
        if (element.offsetParent === null) continue;
        const text = (element.innerText || '').toLowerCase();
        const aria = (element.getAttribute('aria-label') || '').toLowerCase();
        if (texts.some((wanted) => text.includes(wanted) || aria.includes(wanted))) return true;
      }
      return false;
    },
    [...profileSelectors.addPhotoTexts],
  );

  return { hasProfilePicture: !hasAddButton };
};

const setProfilePicture = async (context: ActionContext, media: MediaRef): Promise<boolean> => {
  const { page, files } = context;
  const path = await files.resolvePath(media.id);

  await page.goto(PROFILE_URLS.me, {
    waitUntil: 'domcontentloaded',
    timeout: context.automation.timeoutMs,
  });
  await sleep(3_000);

  let input = page.locator(profileSelectors.fileInput).first();
  if ((await input.count()) === 0) {
    const open = await firstVisible(
      [
        page.getByRole(profileSelectors.choosePicture.role, {
          name: profileSelectors.choosePicture.name,
        }),
      ],
      8_000,
    );
    if (open === null) {
      context.log('Could not open the profile picture dialog');
      return false;
    }
    await clickLike(page, open);
    await sleep(3_000);
    input = page.locator(profileSelectors.fileInput).first();
    if ((await input.count()) === 0) return false;
  }

  await input.setInputFiles(path);
  await sleep(2_000);

  const save = await firstVisible(
    [
      page
        .locator('[role="dialog"]')
        .getByRole(profileSelectors.save.role, { name: profileSelectors.save.name }),
    ],
    8_000,
  );
  if (save !== null) {
    await save.click({ force: true });
    await sleep(2_000);
  }
  return true;
};

const updateBio = async (context: ActionContext, bio: string): Promise<boolean> => {
  const { page } = context;
  await page.goto(PROFILE_URLS.aboutBio, {
    waitUntil: 'domcontentloaded',
    timeout: context.automation.timeoutMs,
  });
  await sleep(3_000);

  let input = await firstVisible([page.locator(profileSelectors.bioInput)], 10_000);
  if (input === null) {
    await page.goto(PROFILE_URLS.about, {
      waitUntil: 'domcontentloaded',
      timeout: context.automation.timeoutMs,
    });
    await sleep(3_000);
    const edit = await firstVisible(
      [page.getByRole(profileSelectors.editIntro.role, { name: profileSelectors.editIntro.name })],
      8_000,
    );
    if (edit === null) {
      context.log('Could not find the bio editor');
      return false;
    }
    await clickLike(page, edit);
    await sleep(2_000);
    input = await firstVisible([page.locator(profileSelectors.anyTextbox)], 8_000);
    if (input === null) return false;
  }

  await input.click({ force: true });
  await sleep(300);
  await input.fill('');
  await page.keyboard.type(bio, { delay: 40 + Math.random() * 60 });
  await sleep(500 + Math.random() * 500);

  const save = await firstVisible(
    [page.getByRole(profileSelectors.save.role, { name: profileSelectors.save.name })],
    5_000,
  );
  if (save !== null) {
    await save.click({ force: true });
    await sleep(2_000);
  }
  return true;
};

export interface AutoSetupInput {
  targetFriends: number;
  connectFriends: boolean;
  bio: string | null;
  profilePicture: MediaRef | null;
}

/**
 * The full first-day routine for a fresh profile: accept what is pending,
 * reach the friend target, add a picture, add a bio. Each step that finds
 * nothing to do says so and moves on.
 */
export const autoSetupProfile = async (
  context: ActionContext,
  input: AutoSetupInput,
): Promise<AutomationResult> => {
  const startedAt = Date.now();
  const { page, automation } = context;
  const details: Record<string, unknown> = {};

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 15, 'Accepting pending friend requests');
  details['requestsAccepted'] = await acceptFriendRequests(context, 100);

  throwIfCancelled(context);
  step(context, 35, 'Counting friends');
  const before = await countFriends(context);
  details['friendsBefore'] = before;

  if (before < input.targetFriends) {
    if (!input.connectFriends || input.targetFriends <= 5) {
      context.log('Skipping suggestions: these profiles will befriend each other');
      details['friendsAdded'] = 0;
    } else {
      step(context, 50, `Adding friends (have ${before}, want ${input.targetFriends})`);
      details['friendsAdded'] = await addFriends(context, input.targetFriends - before);
    }
  } else {
    details['friendsAdded'] = 0;
  }

  throwIfCancelled(context);
  step(context, 70, 'Checking the profile picture');
  const setup = await checkProfileSetup(context);
  details['hadProfilePicture'] = setup.hasProfilePicture;
  if (!setup.hasProfilePicture && input.profilePicture !== null) {
    step(context, 80, 'Uploading the profile picture');
    details['profilePictureSet'] = await setProfilePicture(context, input.profilePicture);
  } else if (!setup.hasProfilePicture) {
    context.log('No picture was provided; attach one to the job to set it');
    details['profilePictureSet'] = false;
  }

  if (input.bio !== null && input.bio !== '') {
    throwIfCancelled(context);
    step(context, 90, 'Writing the bio');
    details['bioUpdated'] = await updateBio(context, input.bio);
  }

  return {
    resourceUrl: PROFILE_URLS.me,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details,
  };
};
