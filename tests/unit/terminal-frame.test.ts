import { describe, expect, it } from 'vitest';
import { packTerminalFrame, unpackTerminalFrame, xtermIndex, xtermRgb } from '@fb/shared';

describe('xterm 256-colour palette', () => {
  it('maps the corners of the colour cube', () => {
    expect(xtermIndex(0, 0, 0)).toBe(16);
    expect(xtermIndex(255, 255, 255)).toBe(231);
    expect(xtermIndex(255, 0, 0)).toBe(196);
    expect(xtermIndex(0, 255, 0)).toBe(46);
    expect(xtermIndex(0, 0, 255)).toBe(21);
  });

  it('prefers the grey ramp for a grey the cube cannot hit', () => {
    // 232 + 12 is the ramp step whose level is exactly 128.
    expect(xtermIndex(128, 128, 128)).toBe(244);
    expect(xtermRgb(244)).toEqual([128, 128, 128]);
  });

  it('gives every index from 16 up a colour that maps back to itself', () => {
    for (let index = 16; index <= 255; index += 1) {
      const [r, g, b] = xtermRgb(index);
      expect(xtermIndex(r, g, b), `index ${index}`).toBe(index);
    }
  });

  it('snaps a colour between two levels to the nearer one', () => {
    // Cube levels are 0, 95, 135, 175, 215, 255.
    expect(xtermRgb(xtermIndex(250, 10, 100))).toEqual([255, 0, 95]);
  });
});

describe('terminal frame', () => {
  const rgba = new Uint8Array([
    255, 0, 0, 255, /* red */ 0, 255, 0, 255 /* green */, 0, 0, 255, 255, /* blue */ 128, 128, 128,
    255 /* grey */,
  ]);

  it('packs a frame as width, height, then one palette index per pixel', () => {
    expect([...packTerminalFrame(rgba, 2, 2)]).toEqual([2, 2, 196, 46, 21, 244]);
  });

  it('unpacks back to opaque pixels in palette colours', () => {
    const frame = unpackTerminalFrame(packTerminalFrame(rgba, 2, 2));
    expect(frame).not.toBeNull();
    expect(frame?.width).toBe(2);
    expect(frame?.height).toBe(2);
    expect([...(frame?.rgba ?? [])]).toEqual([...rgba]);
  });

  it('refuses a frame too large for its one-byte dimensions', () => {
    expect(() => packTerminalFrame(new Uint8Array(256 * 1 * 4), 256, 1)).toThrow(RangeError);
  });

  it('returns null for bytes that are not a whole frame', () => {
    expect(unpackTerminalFrame(new Uint8Array([]))).toBeNull();
    expect(unpackTerminalFrame(new Uint8Array([2, 2, 16]))).toBeNull();
    expect(unpackTerminalFrame(new Uint8Array([0, 0]))).toBeNull();
  });
});
