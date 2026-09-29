import { describe, expect, it } from 'vitest';
import {
  generateTotp,
  base32Decode,
  looksLikeTotpSecret,
} from '../../packages/automation/dist/totp/totp.js';

/**
 * RFC 6238 Appendix B vectors, SHA-1, secret = ASCII "12345678901234567890"
 * (base32 GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ), eight digits.
 */
const SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';

describe('generateTotp', () => {
  it('matches the RFC 6238 test vectors', () => {
    expect(generateTotp(SECRET, { now: 59, digits: 8 })).toBe('94287082');
    expect(generateTotp(SECRET, { now: 1111111109, digits: 8 })).toBe('07081804');
    expect(generateTotp(SECRET, { now: 1234567890, digits: 8 })).toBe('89005924');
    expect(generateTotp(SECRET, { now: 2000000000, digits: 8 })).toBe('69279037');
  });

  it('produces six digits by default', () => {
    const code = generateTotp('JBSWY3DPEHPK3PXP');
    expect(code).toMatch(/^\d{6}$/);
  });

  it('is stable within a 30-second step and changes across it', () => {
    const a = generateTotp(SECRET, { now: 100 });
    const b = generateTotp(SECRET, { now: 119 });
    const c = generateTotp(SECRET, { now: 121 });
    expect(a).toBe(b);
    expect(a).not.toBe(c);
  });

  it('ignores spaces and lowercase in the secret', () => {
    expect(generateTotp('jbsw y3dp ehpk 3pxp', { now: 100 })).toBe(
      generateTotp('JBSWY3DPEHPK3PXP', { now: 100 }),
    );
  });
});

describe('base32Decode', () => {
  it('decodes a known secret to its bytes', () => {
    expect(base32Decode('JBSWY3DPEHPK3PXP').toString('hex')).toBe('48656c6c6f21deadbeef');
  });
});

describe('looksLikeTotpSecret', () => {
  it('accepts base32 and rejects everything else', () => {
    expect(looksLikeTotpSecret('JBSWY3DPEHPK3PXP')).toBe(true);
    expect(looksLikeTotpSecret('jbsw y3dp ehpk 3pxp')).toBe(true);
    expect(looksLikeTotpSecret('mcarsph@2026')).toBe(false);
    expect(looksLikeTotpSecret('')).toBe(false);
    expect(looksLikeTotpSecret(null)).toBe(false);
    expect(looksLikeTotpSecret('short')).toBe(false);
  });
});
