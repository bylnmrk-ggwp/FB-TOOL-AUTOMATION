import { describe, expect, it } from 'vitest';
import {
  issueToken,
  TOKEN_MAX_AGE_MS,
  tokenExpiry,
  verifyToken,
} from '../../apps/server/dist/http/auth/tokens.js';

const SECRET = 'correct horse battery staple';
const NOW = Date.UTC(2026, 9, 8, 12, 0, 0);

describe('tokens', () => {
  it('verifies a token it issued', () => {
    const token = issueToken(SECRET, NOW);
    expect(token).toMatch(/^v1\.\d+\.[A-Za-z0-9_-]+$/);
    expect(verifyToken(SECRET, token, NOW + 1_000)).toBe(true);
  });

  it('refuses a token signed with another secret', () => {
    expect(verifyToken('other', issueToken(SECRET, NOW), NOW)).toBe(false);
  });

  it('refuses a tampered token', () => {
    const [version, issuedAt, signature] = issueToken(SECRET, NOW).split('.');
    expect(verifyToken(SECRET, `${version}.${Number(issuedAt) - 1}.${signature}`, NOW)).toBe(false);
    expect(verifyToken(SECRET, `${version}.${issuedAt}.${signature}x`, NOW)).toBe(false);
    expect(verifyToken(SECRET, `${version}.${issuedAt}.${signature}.extra`, NOW)).toBe(false);
  });

  it('expires after thirty days', () => {
    const token = issueToken(SECRET, NOW);
    expect(verifyToken(SECRET, token, NOW + TOKEN_MAX_AGE_MS - 1)).toBe(true);
    expect(verifyToken(SECRET, token, NOW + TOKEN_MAX_AGE_MS)).toBe(false);
  });

  it('refuses garbage without throwing', () => {
    for (const bad of ['', 'v1', 'v1.abc.def', 'v2.1.abc', 'v1..', `v1.${NOW + 60_000}.sig`]) {
      expect(verifyToken(SECRET, bad, NOW)).toBe(false);
    }
  });

  it('reports the expiry as an ISO date', () => {
    expect(tokenExpiry(NOW)).toBe(new Date(NOW + TOKEN_MAX_AGE_MS).toISOString());
  });
});
