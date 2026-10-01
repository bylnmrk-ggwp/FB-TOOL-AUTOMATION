import type { Page } from 'playwright';
import { AutomationFailedError, sleep, type AutomationResult } from '@fb/shared';
import { idle } from '../humanInput.js';
import { watchScripts } from '../selectors/watch.selectors.js';
import { step, type ActionContext } from './types.js';

export interface WatchLiveInput {
  url: string;
  minutes: number | null;
}

interface Probe {
  video: boolean;
  t: number;
  paused: boolean;
  ended: boolean;
  resumed?: boolean;
  /** The rendition being decoded, so the quality the player settled on is visible. */
  w?: number;
  h?: number;
}

/**
 * The watch scripts are stored as function source. Handed to evaluate as a
 * string they are only read, never called — the page returns the function
 * itself, which does not serialise, so every reading came back undefined
 * and every player looked frozen. Calling them is what runs them.
 */
const run = (page: Page, script: string): Promise<unknown> => page.evaluate(`(${script})()`);

const VIDEO_ID = [/[?&]v=(\d{6,})/, /\/videos\/(\d{6,})/, /video_id=(\d{6,})/];
/** How the id appears inside the page's own data, when the address does not carry it. */
const VIDEO_ID_IN_HTML = [/"videoId":"(\d{6,})"/, /"video_id":"(\d{6,})"/];

/** Headers that make a plain fetch look like the navigation Facebook expects; without them it answers 400. */
const NAVIGATION_HEADERS = {
  accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'accept-language': 'en-US,en;q=0.9',
  'sec-fetch-dest': 'document',
  'sec-fetch-mode': 'navigate',
  'sec-fetch-site': 'none',
  'sec-fetch-user': '?1',
  'upgrade-insecure-requests': '1',
};

const firstMatch = (text: string, patterns: readonly RegExp[]): string | null => {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1] !== undefined) return match[1];
  }
  return null;
};

/**
 * The page a viewer watches on. Facebook's bare embed player plays the same
 * stream with the same session for a little over half the memory of the
 * full live page, which also carries the feed, the chat and everything
 * else a viewer never looks at. The video id comes from the link itself,
 * or from the page the link resolves to — fetched as a document, never
 * rendered — where it sits in the address or in the page data. A link that
 * yields no id is watched as given.
 */
const RESOLVED_TTL_MS = 15 * 60 * 1000;
/** Links already resolved, and resolutions in flight, so a batch asks Facebook once per link. */
const resolved = new Map<string, { at: number; target: Promise<string> }>();

const viewerUrl = (context: ActionContext, url: string): Promise<string> => {
  const known = resolved.get(url);
  if (known !== undefined && Date.now() - known.at < RESOLVED_TTL_MS) return known.target;
  const target = resolveViewerUrl(context, url);
  resolved.set(url, { at: Date.now(), target });
  target.catch(() => resolved.delete(url));
  return target;
};

const resolveViewerUrl = async (context: ActionContext, url: string): Promise<string> => {
  let id = firstMatch(url, VIDEO_ID);
  if (id === null) {
    try {
      const response = await context.page.request.get(url, {
        maxRedirects: 10,
        headers: NAVIGATION_HEADERS,
      });
      id = firstMatch(response.url(), VIDEO_ID);
      if (id === null) id = firstMatch(await response.text(), VIDEO_ID_IN_HTML);
    } catch {
      id = null;
    }
  }
  return id === null ? url : `https://www.facebook.com/video/embed?video_id=${id}&autoplay=1`;
};

const VERIFY_SAMPLE_MS = 4_000;
const POLL_RANGE_MS: [number, number] = [15_000, 50_000];

/**
 * Keeps a live video playing in this account's browser.
 *
 * A page that loaded is not a viewer. Facebook pauses the player when a
 * stream cuts over, and a page under load stalls with `paused` still false,
 * so the check is whether `currentTime` moves. Each round resumes anything
 * paused, kicks a frozen player back to the live edge, and reloads a page
 * that lost its player. The job ends at the time limit, when the broadcast
 * ends, or when it is cancelled.
 */
export const watchLive = async (
  context: ActionContext,
  input: WatchLiveInput,
): Promise<AutomationResult> => {
  const startedAt = Date.now();
  const { page, navigation, automation, log } = context;
  const deadline = input.minutes === null ? null : startedAt + input.minutes * 60_000;

  step(context, 5, 'Checking the session');
  await context.session.assertUsable(page, automation.accountId);

  step(context, 10, 'Opening the live video');
  const target = await viewerUrl(context, input.url);
  if (target !== input.url) log(`Watching through the embed player: ${target}`);
  await navigation.goto(page, target);
  await sleep(3_000);

  const verdict = await verifyPlaying(context);
  if (verdict !== 'playing')
    throw new AutomationFailedError(`Not watching: ${verdict}`, { url: input.url });
  await run(page, watchScripts.kick);
  await run(page, watchScripts.slim).catch(() => undefined);

  step(
    context,
    20,
    input.minutes === null
      ? 'Watching until the broadcast ends'
      : `Watching for ${input.minutes} min`,
  );

  let lastTime = 0;
  let stalls = 0;
  let rounds = 0;
  let reloads = 0;
  while (true) {
    // Between checks the viewer behaves like one: the cursor drifts now and
    // then at no fixed cadence. No scrolling — the player must stay in view.
    await idle(page, POLL_RANGE_MS[0] + Math.random() * (POLL_RANGE_MS[1] - POLL_RANGE_MS[0]), {
      signal: automation.signal,
      scroll: false,
    });
    rounds += 1;

    if (deadline !== null && Date.now() >= deadline) {
      log('Time limit reached');
      break;
    }

    let probe: Probe;
    try {
      probe = (await run(page, watchScripts.probe)) as Probe;
    } catch {
      // A renderer that cannot be asked anything is not watching; rebuild it.
      log('The page stopped answering; reloading');
      await navigation.goto(page, target);
      reloads += 1;
      continue;
    }

    if (!probe.video) {
      if (await broadcastEnded(context)) {
        log('The broadcast has ended');
        break;
      }
      log('The player is gone; reloading');
      await navigation.goto(page, target);
      await run(page, watchScripts.slim).catch(() => undefined);
      reloads += 1;
      lastTime = 0;
      continue;
    }

    if (probe.resumed === true) log('Resumed a paused player');

    if (probe.t - lastTime < 0.5 && rounds > 1) {
      stalls += 1;
      log(`The player is not advancing (${stalls})`);
      await run(page, watchScripts.kick);
      if (stalls >= 3) {
        log('Still frozen after kicks; reloading');
        await navigation.goto(page, target);
        await run(page, watchScripts.slim).catch(() => undefined);
        reloads += 1;
        stalls = 0;
      }
    } else {
      stalls = 0;
    }
    lastTime = probe.t;

    const elapsed = Math.round((Date.now() - startedAt) / 60_000);
    const total = input.minutes === null ? null : Math.round(input.minutes);
    const progress =
      total === null ? 50 : Math.min(95, 20 + Math.round((75 * elapsed) / Math.max(1, total)));
    const viewers = await run(page, watchScripts.viewers).catch(() => null);
    const rendition =
      probe.w !== undefined && probe.h !== undefined && probe.w > 0
        ? `, ${probe.w}x${probe.h}`
        : '';
    automation.onProgress(
      progress,
      viewers === null
        ? `Watching, ${elapsed} min${rendition}`
        : `Watching, ${elapsed} min${rendition}, ${String(viewers)} viewers`,
    );
  }

  return {
    resourceUrl: input.url,
    durationMs: Date.now() - startedAt,
    screenshotPath: null,
    details: { minutesWatched: Math.round((Date.now() - startedAt) / 60_000), reloads, rounds },
  };
};

/** 'playing', or the reason this page is not a viewer. */
const verifyPlaying = async (context: ActionContext): Promise<string> => {
  const { page } = context;

  if (await context.session.loginOverlayPresent(page)) {
    const verdict = await context.session.classify(page);
    return `login gate: ${verdict.reason ?? verdict.status}`;
  }

  try {
    await page.waitForSelector('video', { timeout: 20_000 });
  } catch {
    if (await broadcastEnded(context)) return 'the broadcast has already ended';
    // Facebook shows this instead of a player when the browser cannot decode
    // the stream — a Chromium build without H.264, typically.
    if (await pageSays(context, 'trouble playing this video'))
      return 'Facebook cannot play this video in this browser (a Chromium without H.264?)';
    return 'no video player on the page';
  }

  const first = (await run(page, watchScripts.currentTime)) as number | null;
  await sleep(VERIFY_SAMPLE_MS);
  const second = (await run(page, watchScripts.currentTime)) as number | null;
  if (first === null || second === null) return 'the player disappeared';
  if (second - first >= 0.5) return 'playing';

  await run(page, watchScripts.kick);
  await sleep(VERIFY_SAMPLE_MS);
  const third = ((await run(page, watchScripts.currentTime)) as number | null) ?? second;
  if (third - second >= 0.5) return 'playing';

  // A broadcast that ended leaves its player on the page, stopped: say so
  // rather than calling the machine frozen.
  if (await broadcastEnded(context)) return 'the broadcast has already ended';
  const probe = (await run(page, watchScripts.probe).catch(() => null)) as Probe | null;
  const state =
    probe === null
      ? ''
      : `, paused ${String(probe.paused)}, ended ${String(probe.ended)}, at ${first.toFixed(1)}s then ${third.toFixed(1)}s`;
  return `the video is frozen (loaded but not advancing${state})`;
};

const pageSays = async (context: ActionContext, text: string): Promise<boolean> => {
  const body = (
    await context.page
      .locator('body')
      .innerText({ timeout: 3_000 })
      .catch(() => '')
  ).toLowerCase();
  return body.includes(text);
};

const broadcastEnded = async (context: ActionContext): Promise<boolean> => {
  const body = (
    await context.page
      .locator('body')
      .innerText({ timeout: 3_000 })
      .catch(() => '')
  ).toLowerCase();
  return watchScripts.endedTexts.some((text) => body.includes(text));
};
