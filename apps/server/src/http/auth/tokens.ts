import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * A token is `v1.<issuedAtMs>.<signature>`: a signed timestamp, nothing more.
 * The server keeps no session table, so a restart does not log anyone out
 * and there is nothing to garbage-collect. Rotating the secret ends every
 * session at once.
 */
export const TOKEN_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

const VERSION = 'v1';

const sign = (secret: string, issuedAt: string): string =>
  createHmac('sha256', secret).update(`${VERSION}.${issuedAt}`).digest('base64url');

export const issueToken = (secret: string, nowMs: number): string => {
  const issuedAt = String(Math.floor(nowMs));
  return `${VERSION}.${issuedAt}.${sign(secret, issuedAt)}`;
};

export const verifyToken = (secret: string, token: string, nowMs: number): boolean => {
  const parts = token.split('.');
  if (parts.length !== 3) return false;
  const [version, issuedAt, signature] = parts as [string, string, string];
  if (version !== VERSION || !/^\d+$/.test(issuedAt) || signature.length === 0) return false;

  const issuedAtMs = Number(issuedAt);
  if (issuedAtMs > nowMs || nowMs - issuedAtMs >= TOKEN_MAX_AGE_MS) return false;

  const expected = Buffer.from(sign(secret, issuedAt));
  const given = Buffer.from(signature);
  return expected.length === given.length && timingSafeEqual(expected, given);
};

export const tokenExpiry = (nowMs: number): string =>
  new Date(nowMs + TOKEN_MAX_AGE_MS).toISOString();
