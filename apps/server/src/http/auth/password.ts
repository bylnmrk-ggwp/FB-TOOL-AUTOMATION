import { createHash, timingSafeEqual } from 'node:crypto';

/**
 * Both sides are hashed first so the comparison runs over equal-length
 * buffers and takes the same time whether the first or the last byte differs.
 */
export const passwordMatches = (given: string, expected: string): boolean => {
  const digest = (value: string): Buffer => createHash('sha256').update(value, 'utf8').digest();
  return timingSafeEqual(digest(given), digest(expected));
};
