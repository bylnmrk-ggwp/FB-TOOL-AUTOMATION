import { inflateSync } from 'node:zlib';

export interface DecodedImage {
  width: number;
  height: number;
  /** Four bytes per pixel, row by row from the top. */
  rgba: Uint8Array;
}

const SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a] as const;

const paeth = (a: number, b: number, c: number): number => {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
};

/**
 * Reads the PNGs Chromium writes for a screenshot: 8 bits per channel, RGB or
 * RGBA, not interlaced. That is the whole of what the terminal frame needs,
 * so anything else is refused rather than half-read. Checksums are not
 * verified; the bytes come straight from the browser over a local pipe.
 */
export const decodePng = (bytes: Uint8Array): DecodedImage => {
  if (bytes.length < SIGNATURE.length || SIGNATURE.some((byte, i) => bytes[i] !== byte)) {
    throw new Error('Not a PNG');
  }

  const view = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let width = 0;
  let height = 0;
  let channels = 0;
  const data: Buffer[] = [];

  for (let offset = SIGNATURE.length; offset + 8 <= view.length;) {
    const length = view.readUInt32BE(offset);
    const type = view.toString('ascii', offset + 4, offset + 8);
    const body = view.subarray(offset + 8, offset + 8 + length);
    offset += 12 + length;

    if (type === 'IHDR') {
      width = body.readUInt32BE(0);
      height = body.readUInt32BE(4);
      const bitDepth = body[8];
      const colourType = body[9];
      const interlace = body[12];
      if (bitDepth !== 8 || (colourType !== 2 && colourType !== 6) || interlace !== 0) {
        throw new Error(
          `Unsupported PNG layout: depth ${bitDepth}, colour type ${colourType}, interlace ${interlace}`,
        );
      }
      channels = colourType === 6 ? 4 : 3;
    } else if (type === 'IDAT') {
      data.push(body);
    } else if (type === 'IEND') {
      break;
    }
  }

  if (width === 0 || height === 0 || channels === 0) throw new Error('Not a PNG: no header');

  const stride = width * channels;
  const raw = inflateSync(Buffer.concat(data));
  if (raw.length < (stride + 1) * height) throw new Error('Not a PNG: image data is short');

  const rgba = new Uint8Array(width * height * 4);
  let previous = new Uint8Array(stride);
  for (let y = 0; y < height; y += 1) {
    const start = y * (stride + 1);
    const filter = raw[start] ?? 0;
    const row = new Uint8Array(stride);

    for (let i = 0; i < stride; i += 1) {
      const value = raw[start + 1 + i] ?? 0;
      const a = i >= channels ? (row[i - channels] ?? 0) : 0;
      const b = previous[i] ?? 0;
      const c = i >= channels ? (previous[i - channels] ?? 0) : 0;
      const predicted =
        filter === 1
          ? a
          : filter === 2
            ? b
            : filter === 3
              ? Math.floor((a + b) / 2)
              : filter === 4
                ? paeth(a, b, c)
                : 0;
      row[i] = (value + predicted) & 0xff;
    }

    for (let x = 0; x < width; x += 1) {
      const from = x * channels;
      const to = (y * width + x) * 4;
      rgba[to] = row[from] ?? 0;
      rgba[to + 1] = row[from + 1] ?? 0;
      rgba[to + 2] = row[from + 2] ?? 0;
      rgba[to + 3] = channels === 4 ? (row[from + 3] ?? 255) : 255;
    }
    previous = row;
  }

  return { width, height, rgba };
};
