/**
 * A browser page as a terminal would show it: a small grid of pixels, each
 * one of the 256 colours an xterm can paint. One byte per pixel makes a frame
 * a few kilobytes where a JPEG thumbnail is tens of them, which matters when
 * twenty tiles refresh over a phone connection.
 *
 * Wire format: `[width, height, index, index, …]`, row by row from the top.
 */

/** The six levels of each channel in the xterm colour cube (indexes 16–231). */
const CUBE_LEVELS = [0, 95, 135, 175, 215, 255] as const;
/** The grey ramp (indexes 232–255) runs 8, 18, … 238. */
const GREY_START = 8;
const GREY_STEP = 10;
const GREY_STEPS = 24;

/** The sixteen named colours below the cube. A packed frame never uses them. */
const BASIC: readonly (readonly [number, number, number])[] = [
  [0, 0, 0],
  [128, 0, 0],
  [0, 128, 0],
  [128, 128, 0],
  [0, 0, 128],
  [128, 0, 128],
  [0, 128, 128],
  [192, 192, 192],
  [128, 128, 128],
  [255, 0, 0],
  [0, 255, 0],
  [255, 255, 0],
  [0, 0, 255],
  [255, 0, 255],
  [0, 255, 255],
  [255, 255, 255],
];

const nearestCubeStep = (value: number): number => {
  let best = 0;
  let bestDistance = Infinity;
  for (let step = 0; step < CUBE_LEVELS.length; step += 1) {
    const distance = Math.abs((CUBE_LEVELS[step] ?? 0) - value);
    if (distance < bestDistance) {
      best = step;
      bestDistance = distance;
    }
  }
  return best;
};

const level = (step: number): number => CUBE_LEVELS[step] ?? 0;

/** The xterm index (16–255) closest to an RGB colour. */
export const xtermIndex = (r: number, g: number, b: number): number => {
  const rs = nearestCubeStep(r);
  const gs = nearestCubeStep(g);
  const bs = nearestCubeStep(b);
  const cubeDistance = (level(rs) - r) ** 2 + (level(gs) - g) ** 2 + (level(bs) - b) ** 2;

  const average = (r + g + b) / 3;
  const greyStep = Math.min(
    GREY_STEPS - 1,
    Math.max(0, Math.round((average - GREY_START) / GREY_STEP)),
  );
  const grey = GREY_START + GREY_STEP * greyStep;
  const greyDistance = (grey - r) ** 2 + (grey - g) ** 2 + (grey - b) ** 2;

  // A tie goes to the cube, so a cube colour always maps back to itself.
  return greyDistance < cubeDistance ? 232 + greyStep : 16 + 36 * rs + 6 * gs + bs;
};

/** The RGB colour an xterm paints for an index. */
export const xtermRgb = (index: number): [number, number, number] => {
  if (index >= 232) {
    const grey = GREY_START + GREY_STEP * Math.min(GREY_STEPS - 1, index - 232);
    return [grey, grey, grey];
  }
  if (index >= 16) {
    const offset = index - 16;
    return [level(Math.floor(offset / 36)), level(Math.floor(offset / 6) % 6), level(offset % 6)];
  }
  const [r, g, b] = BASIC[Math.max(0, index)] ?? [0, 0, 0];
  return [r, g, b];
};

export interface TerminalFrame {
  width: number;
  height: number;
  /** Opaque RGBA, ready for a canvas. */
  rgba: Uint8ClampedArray;
}

/** Packs RGBA pixels into the wire format. Dimensions must fit one byte each. */
export const packTerminalFrame = (
  rgba: Uint8Array | Uint8ClampedArray,
  width: number,
  height: number,
): Uint8Array => {
  if (
    !Number.isInteger(width) ||
    !Number.isInteger(height) ||
    width < 1 ||
    height < 1 ||
    width > 255 ||
    height > 255
  ) {
    throw new RangeError(`A terminal frame is 1–255 pixels each way, not ${width}×${height}`);
  }
  if (rgba.length < width * height * 4) {
    throw new RangeError(`Expected ${width * height * 4} bytes of RGBA, got ${rgba.length}`);
  }

  const frame = new Uint8Array(2 + width * height);
  frame[0] = width;
  frame[1] = height;
  for (let pixel = 0; pixel < width * height; pixel += 1) {
    const at = pixel * 4;
    frame[2 + pixel] = xtermIndex(rgba[at] ?? 0, rgba[at + 1] ?? 0, rgba[at + 2] ?? 0);
  }
  return frame;
};

/** Reads the wire format back into pixels. Null when the bytes are not a whole frame. */
export const unpackTerminalFrame = (bytes: Uint8Array): TerminalFrame | null => {
  const width = bytes[0];
  const height = bytes[1];
  if (width === undefined || height === undefined || width === 0 || height === 0) return null;
  if (bytes.length !== 2 + width * height) return null;

  const rgba = new Uint8ClampedArray(width * height * 4);
  for (let pixel = 0; pixel < width * height; pixel += 1) {
    const [r, g, b] = xtermRgb(bytes[2 + pixel] ?? 16);
    const at = pixel * 4;
    rgba[at] = r;
    rgba[at + 1] = g;
    rgba[at + 2] = b;
    rgba[at + 3] = 255;
  }
  return { width, height, rgba };
};
