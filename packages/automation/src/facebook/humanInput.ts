import type { Locator, Page } from 'playwright';
import { randomDelayMs, sleep } from '@fb/shared';

/**
 * Mouse and keyboard input with human timing and human paths.
 *
 * `locator.fill()` writes a field in one DOM assignment and `locator.click()`
 * lands the pointer on an element's exact centre. Neither produces what a
 * person cannot help producing: travel between two points, a cursor that
 * lands off-centre, keystrokes spaced unevenly, a pause before a button.
 * Anti-bot scoring reads exactly those signals, and a poor score is what puts
 * an "I'm not a robot" box in front of a login.
 *
 * Nothing here defeats a challenge. It only stops the automation from looking
 * mechanical while it types a password the operator owns.
 */

const KEY_MIN_MS = 55;
const KEY_MAX_MS = 190;
const WORD_PAUSE_MS: [number, number] = [180, 450];
const THINK_PAUSE_MS: [number, number] = [400, 1100];
const MOVE_STEP_PX = 55;
const MOVE_STEPS = { min: 8, max: 28 };
const CLICK_HOLD_MS: [number, number] = [50, 140];

const positions = new WeakMap<Page, { x: number; y: number }>();

const pointerOf = (page: Page): { x: number; y: number } =>
  positions.get(page) ?? { x: randomDelayMs(60, 400), y: randomDelayMs(60, 400) };

/**
 * Points along a quadratic Bezier from start to target. A hand arcs and
 * settles; a straight line of evenly spaced points is as machine-readable as
 * no movement at all.
 */
const curve = (
  from: { x: number; y: number },
  to: { x: number; y: number },
  steps: number,
): Array<{ x: number; y: number }> => {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const distance = Math.hypot(dx, dy) || 1;
  const bow = (Math.random() < 0.5 ? -1 : 1) * (0.07 + Math.random() * 0.13) * distance;
  const cx = (from.x + to.x) / 2 - (dy / distance) * bow;
  const cy = (from.y + to.y) / 2 + (dx / distance) * bow;

  const points = [];
  for (let i = 1; i <= steps; i += 1) {
    let t = i / steps;
    t = t * t * (3 - 2 * t);
    const u = 1 - t;
    let x = u * u * from.x + 2 * u * t * cx + t * t * to.x;
    let y = u * u * from.y + 2 * u * t * cy + t * t * to.y;
    if (i < steps) {
      x += Math.random() * 3 - 1.5;
      y += Math.random() * 3 - 1.5;
    }
    points.push({ x, y });
  }
  return points;
};

export const moveTo = async (page: Page, x: number, y: number): Promise<void> => {
  const from = pointerOf(page);
  const distance = Math.hypot(x - from.x, y - from.y);
  const steps = Math.round(
    Math.min(MOVE_STEPS.max, Math.max(MOVE_STEPS.min, (distance / MOVE_STEP_PX) * 8)),
  );

  for (const point of curve(from, { x, y }, steps)) {
    await page.mouse.move(point.x, point.y);
    await sleep(randomDelayMs(6, 22));
  }
  positions.set(page, { x, y });
};

/**
 * Moves to an element and presses it like a person would. Returns false when
 * the element has no box to aim at, so the caller can fall back to a plain
 * click.
 */
export const humanClick = async (page: Page, target: Locator): Promise<boolean> => {
  try {
    await target.scrollIntoViewIfNeeded();
  } catch {
    // Off-screen and unscrollable: the box check below reports it.
  }

  const box = await target.boundingBox().catch(() => null);
  if (box === null || box.width === 0 || box.height === 0) return false;

  // Somewhere in the middle third, never the exact centre.
  const x = box.x + box.width * (0.3 + Math.random() * 0.4);
  const y = box.y + box.height * (0.3 + Math.random() * 0.4);

  await moveTo(page, x, y);
  await sleep(randomDelayMs(40, 160));
  await page.mouse.down();
  await sleep(randomDelayMs(...CLICK_HOLD_MS));
  await page.mouse.up();
  return true;
};

/** Click with the human path when possible, Playwright's own click otherwise. */
export const clickLike = async (page: Page, target: Locator, timeoutMs = 8_000): Promise<void> => {
  if (await humanClick(page, target)) return;
  await target.click({ timeout: timeoutMs });
};

/**
 * Types into a field one character at a time, with the pauses a person
 * takes: a beat after a separator, an occasional longer stop.
 */
export const humanType = async (page: Page, field: Locator, text: string): Promise<void> => {
  await clickLike(page, field);
  await sleep(randomDelayMs(120, 380));

  const think = Math.random() < 0.33 ? Math.floor(Math.random() * text.length) : -1;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index] ?? '';
    await page.keyboard.type(character, { delay: 0 });

    let pause = randomDelayMs(KEY_MIN_MS, KEY_MAX_MS);
    if ('@._- '.includes(character)) pause += randomDelayMs(...WORD_PAUSE_MS);
    if (index === think) pause += randomDelayMs(...THINK_PAUSE_MS);
    await sleep(pause);
  }
};

/**
 * A reader's pause after a page opens, before anything is touched. Given the
 * page, the cursor usually drifts across it first — a person looks before
 * they reach for a field.
 */
export const settle = async (page?: Page): Promise<void> => {
  await sleep(randomDelayMs(900, 2_400));
  if (page !== undefined && Math.random() < 0.6) {
    await wander(page).catch(() => undefined);
  }
};

/** Viewport in CSS pixels, from the page itself; a safe default when it cannot say. */
const viewportOf = async (page: Page): Promise<{ width: number; height: number }> => {
  const size = page.viewportSize();
  if (size !== null) return size;
  try {
    return await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
  } catch {
    return { width: 1200, height: 800 };
  }
};

/**
 * The cursor drifts to one to three places a reader's hand might rest: over
 * the content, near the edge, back again. Never the same path twice.
 */
export const wander = async (page: Page): Promise<void> => {
  const { width, height } = await viewportOf(page);
  const stops = 1 + Math.floor(Math.random() * 3);
  for (let i = 0; i < stops; i += 1) {
    const x = width * (0.08 + Math.random() * 0.84);
    const y = height * (0.1 + Math.random() * 0.8);
    await moveTo(page, x, y);
    await sleep(randomDelayMs(250, 1_400));
  }
};

/**
 * Wheel scrolling in the short bursts a person makes — a few notches, a
 * glance, a few more — and now and then a scroll back up to re-read.
 */
export const scrollAround = async (page: Page): Promise<void> => {
  const down = Math.random() < 0.8;
  const bursts = 1 + Math.floor(Math.random() * 3);
  for (let i = 0; i < bursts; i += 1) {
    const notches = 1 + Math.floor(Math.random() * 4);
    for (let n = 0; n < notches; n += 1) {
      await page.mouse.wheel(0, (down ? 1 : -1) * randomDelayMs(60, 140));
      await sleep(randomDelayMs(30, 110));
    }
    await sleep(randomDelayMs(400, 1_600));
  }
  if (down && Math.random() < 0.3) {
    await sleep(randomDelayMs(600, 1_800));
    await page.mouse.wheel(0, -randomDelayMs(120, 360));
  }
};

export interface IdleOptions {
  /** Cuts the wait short when the job is cancelled. */
  signal?: AbortSignal;
  /** Whether the page may be scrolled while idling; off when a dialog is open. */
  scroll?: boolean;
}

/**
 * Waits `ms` the way a person waits on a page: mostly still, with the cursor
 * drifting or the page scrolled a little at irregular moments. The gaps
 * between those moments are drawn fresh each time — there is no rhythm to
 * pick out — and a long stretch of doing nothing is as likely as a fidget.
 *
 * Any micro-action that fails (the page navigated, a dialog took the wheel)
 * is dropped silently; idling must never be the reason a job fails.
 */
export const idle = async (page: Page, ms: number, options: IdleOptions = {}): Promise<void> => {
  const scroll = options.scroll ?? true;
  const signal = options.signal;
  const until = Date.now() + ms;

  const rest = async (duration: number): Promise<void> => {
    const slice = 250;
    let waited = 0;
    while (waited < duration) {
      if (signal?.aborted === true) throw new DOMException('The job was cancelled', 'AbortError');
      const next = Math.min(slice, duration - waited);
      await sleep(next);
      waited += next;
    }
  };

  while (Date.now() < until) {
    const remaining = until - Date.now();
    // A stretch of stillness: usually a few seconds, sometimes a long look.
    const still = Math.random() < 0.2 ? randomDelayMs(9_000, 22_000) : randomDelayMs(1_800, 8_500);
    await rest(Math.min(still, remaining));
    if (Date.now() >= until) break;

    try {
      const roll = Math.random();
      if (scroll && roll < 0.45) await scrollAround(page);
      else if (roll < 0.9) await wander(page);
      // Otherwise: nothing at all this time.
    } catch {
      // The page moved on; the wait itself still stands.
    }
  }
};
