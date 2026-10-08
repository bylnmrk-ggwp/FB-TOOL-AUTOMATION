import type { Page } from 'playwright';
import { packTerminalFrame } from '@fb/shared';
import { decodePng } from './png.js';

/** How many pixels wide a frame is. Two of them stack into one terminal cell. */
export const TERMINAL_COLUMNS = 120;
/** The grid's tiles are 16:10; a taller page is cut at that line, not squashed. */
const TILE_ASPECT = 10 / 16;
const CAPTURE_TIMEOUT_MS = 5_000;

const withTimeout = async <T>(work: Promise<T>, ms: number): Promise<T> => {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      work,
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error(`Timed out after ${ms}ms`)), ms);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
};

/**
 * The top of a page as a packed terminal frame.
 *
 * Chromium does the shrinking: the screenshot is asked for at the frame's own
 * size through the DevTools protocol, so the server only ever handles a
 * 120-pixel-wide image and never decodes a full-size one.
 */
export const captureTerminalFrame = async (page: Page): Promise<Uint8Array> => {
  const size =
    page.viewportSize() ??
    ((await page.evaluate('({ width: window.innerWidth, height: window.innerHeight })')) as {
      width: number;
      height: number;
    });
  const width = Math.max(1, Math.round(size.width));
  const height = Math.max(1, Math.min(Math.round(size.height), Math.round(width * TILE_ASPECT)));

  const session = await page.context().newCDPSession(page);
  try {
    const shot = await withTimeout(
      session.send('Page.captureScreenshot', {
        format: 'png',
        clip: { x: 0, y: 0, width, height, scale: TERMINAL_COLUMNS / width },
      }),
      CAPTURE_TIMEOUT_MS,
    );
    const image = decodePng(Buffer.from(shot.data, 'base64'));
    return packTerminalFrame(image.rgba, image.width, image.height);
  } finally {
    await session.detach().catch(() => undefined);
  }
};
