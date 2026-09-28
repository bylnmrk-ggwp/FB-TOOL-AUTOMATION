import { dirname, isAbsolute, join, normalize, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * The repository root, found by walking up from this file. Every configured
 * path is resolved against it so relative values in .env behave the same no
 * matter which directory the process was started from.
 */
export const repoRoot = (): string => {
  const here = dirname(fileURLToPath(import.meta.url));
  // src/config -> src -> apps/server -> apps -> <root>
  return resolve(here, '..', '..', '..', '..');
};

export const resolveFromRoot = (value: string): string =>
  isAbsolute(value) ? normalize(value) : resolve(repoRoot(), value);

/**
 * Joins `segment` onto `root` and refuses anything that lands outside it.
 * This is the single guard against path traversal from user input.
 */
export const resolveInside = (root: string, segment: string): string | null => {
  const target = normalize(join(root, segment));
  const rel = relative(root, target);
  if (rel === '' || rel.startsWith('..') || isAbsolute(rel)) return null;
  if (rel.split(sep).some((part) => part === '..')) return null;
  return target;
};
