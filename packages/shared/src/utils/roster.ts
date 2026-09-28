const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;

/**
 * The account identifier inside a roster USERNAME cell, without the notes.
 *
 * A roster is edited by hand: a tick next to a finished account, a remark
 * beside one that would not open, an invisible formatting mark pasted in
 * from elsewhere. Typed into Facebook as-is, those notes make the sign-in
 * fail. An email anywhere in the cell wins; otherwise the cell's own text,
 * minus invisible characters and outer whitespace, is the identifier.
 */
export const cleanUsername = (raw: string): string => {
  const visible = raw.replace(/\p{Cf}/gu, '');
  const email = EMAIL.exec(visible);
  return email === null ? visible.trim() : email[0];
};

/** One entry from a pool, or null when the pool is empty. */
export const randomChoice = <T>(pool: readonly T[]): T | null => {
  if (pool.length === 0) return null;
  const index = Math.floor(Math.random() * pool.length);
  return pool[index] ?? null;
};
