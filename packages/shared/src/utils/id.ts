const ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz';

/**
 * Prefixed, sortable-enough identifier: `acc_lq3k1f_8f2a`.
 * The prefix makes ids self-describing in logs without another lookup.
 */
export const createId = (prefix: string): string => {
  const time = Date.now().toString(36);
  // globalThis.crypto is available in Node >= 19 and in every supported browser,
  // which keeps this package free of Node-only imports.
  const random = globalThis.crypto.randomUUID().replace(/-/g, '').slice(0, 8);
  return `${prefix}_${time}_${random}`;
};

/** Turns a display name into a filesystem-safe profile slug. */
export const slugify = (value: string, fallback = 'account'): string => {
  const slug = value
    .normalize('NFKD')
    // NFKD splits an accented letter into letter + combining mark; dropping the
    // marks turns "Ünïcode" into "unicode" instead of "u-ni-code".
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
  if (slug.length >= 3) return slug;
  const suffix = Array.from({ length: 4 }, () => {
    const index = Math.floor(Math.random() * ALPHABET.length);
    return ALPHABET[index] ?? '0';
  }).join('');
  return `${fallback}-${suffix}`;
};
