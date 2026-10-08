import { deflateSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import { decodePng } from '../../packages/automation/dist/browser/png.js';

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

const chunk = (type: string, data: Buffer): Buffer => {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  // The decoder does not check the CRC, so four zero bytes stand in for it.
  return Buffer.concat([length, Buffer.from(type, 'ascii'), data, Buffer.alloc(4)]);
};

const paeth = (a: number, b: number, c: number): number => {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
};

/** A reference PNG encoder: one filter type for every scanline. */
const encodePng = (
  pixels: number[][],
  width: number,
  channels: 3 | 4,
  filter: 0 | 1 | 2 | 3 | 4,
  options: { splitIdat?: boolean } = {},
): Uint8Array => {
  const stride = width * channels;
  const raw: number[] = [];
  let previous = new Array<number>(stride).fill(0);
  for (const row of pixels) {
    raw.push(filter);
    for (let i = 0; i < stride; i += 1) {
      const x = row[i] ?? 0;
      const a = i >= channels ? (row[i - channels] ?? 0) : 0;
      const b = previous[i] ?? 0;
      const c = i >= channels ? (previous[i - channels] ?? 0) : 0;
      const predicted = [0, a, b, Math.floor((a + b) / 2), paeth(a, b, c)][filter] ?? 0;
      raw.push((x - predicted) & 0xff);
    }
    previous = row;
  }

  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(pixels.length, 4);
  header[8] = 8; // bit depth
  header[9] = channels === 4 ? 6 : 2; // colour type
  const data = deflateSync(Buffer.from(raw));
  const idat = options.splitIdat
    ? [chunk('IDAT', data.subarray(0, 5)), chunk('IDAT', data.subarray(5))]
    : [chunk('IDAT', data)];

  return new Uint8Array(
    Buffer.concat([SIGNATURE, chunk('IHDR', header), ...idat, chunk('IEND', Buffer.alloc(0))]),
  );
};

const RGBA_ROWS = [
  [10, 20, 30, 255, 200, 100, 50, 255, 0, 0, 0, 255],
  [250, 240, 230, 255, 5, 15, 25, 255, 90, 180, 45, 255],
  [1, 2, 3, 255, 255, 255, 255, 255, 128, 64, 32, 255],
];

describe('decodePng', () => {
  it.each([0, 1, 2, 3, 4] as const)('undoes filter type %i on an RGBA image', (filter) => {
    const image = decodePng(encodePng(RGBA_ROWS, 3, 4, filter));
    expect(image.width).toBe(3);
    expect(image.height).toBe(3);
    expect([...image.rgba]).toEqual(RGBA_ROWS.flat());
  });

  it('expands an RGB image to opaque RGBA', () => {
    const rows = [
      [10, 20, 30, 200, 100, 50],
      [250, 240, 230, 5, 15, 25],
    ];
    const image = decodePng(encodePng(rows, 2, 3, 4));
    expect([...image.rgba]).toEqual([
      10, 20, 30, 255, 200, 100, 50, 255, 250, 240, 230, 255, 5, 15, 25, 255,
    ]);
  });

  it('joins image data split across several IDAT chunks', () => {
    const image = decodePng(encodePng(RGBA_ROWS, 3, 4, 1, { splitIdat: true }));
    expect([...image.rgba]).toEqual(RGBA_ROWS.flat());
  });

  it('refuses bytes that are not a PNG', () => {
    expect(() => decodePng(new Uint8Array([0xff, 0xd8, 0xff]))).toThrow(/not a PNG/i);
  });

  it('refuses a PNG layout it does not read', () => {
    const png = Buffer.from(encodePng(RGBA_ROWS, 3, 4, 0));
    png[8 + 8 + 9] = 3; // colour type: palette
    expect(() => decodePng(new Uint8Array(png))).toThrow(/unsupported/i);
  });
});
