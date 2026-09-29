import { createHmac } from 'node:crypto';

/**
 * A time-based one-time password (RFC 6238), the six digits an authenticator
 * app shows. Given the account's base32 secret it is computed here, so a
 * login that hits two-factor can answer it without a person or a phone.
 *
 * No dependency: it is one HMAC over the time counter, which node:crypto
 * already provides.
 */

/** Decodes an RFC 4648 base32 secret (the form authenticators export). */
export const base32Decode = (input: string): Buffer => {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const clean = input
    .toUpperCase()
    .replace(/=+$/, '')
    .replace(/\s+/g, '')
    .replace(/0/g, 'O')
    .replace(/1/g, 'I');
  let bits = 0;
  let value = 0;
  const bytes: number[] = [];
  for (const char of clean) {
    const index = alphabet.indexOf(char);
    if (index === -1) continue;
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((value >>> bits) & 0xff);
    }
  }
  return Buffer.from(bytes);
};

export interface TotpOptions {
  digits?: number;
  periodSeconds?: number;
  /** Unix seconds; defaults to now. Injectable so a test can pin the counter. */
  now?: number;
  algorithm?: 'sha1' | 'sha256' | 'sha512';
}

/** The current TOTP code for a base32 secret. */
export const generateTotp = (secret: string, options: TotpOptions = {}): string => {
  const digits = options.digits ?? 6;
  const period = options.periodSeconds ?? 30;
  const nowSeconds = options.now ?? Math.floor(Date.now() / 1000);
  const counter = Math.floor(nowSeconds / period);

  const key = base32Decode(secret);
  const message = Buffer.alloc(8);
  // 64-bit big-endian counter; the high word is zero for any realistic time.
  message.writeUInt32BE(Math.floor(counter / 0x100000000), 0);
  message.writeUInt32BE(counter >>> 0, 4);

  const hmac = createHmac(options.algorithm ?? 'sha1', key)
    .update(message)
    .digest();
  const offset = (hmac[hmac.length - 1] ?? 0) & 0x0f;
  const binary =
    (((hmac[offset] ?? 0) & 0x7f) << 24) |
    (((hmac[offset + 1] ?? 0) & 0xff) << 16) |
    (((hmac[offset + 2] ?? 0) & 0xff) << 8) |
    ((hmac[offset + 3] ?? 0) & 0xff);

  return (binary % 10 ** digits).toString().padStart(digits, '0');
};

/** True when a string could be a base32 secret worth trying. */
export const looksLikeTotpSecret = (value: string | null | undefined): boolean => {
  const clean = (value ?? '').replace(/\s+/g, '').replace(/=+$/, '');
  return clean.length >= 8 && /^[A-Za-z2-7]+$/.test(clean);
};
