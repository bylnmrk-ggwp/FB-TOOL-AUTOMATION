/**
 * SQLite binds at most 32,766 parameters to one statement. A multi-row
 * insert spends one per column per row, so a roster-sized batch (a job for
 * each of two thousand accounts, eighteen columns each) blows past it in one
 * statement. Writes go in slices small enough never to get near the limit.
 */
export const INSERT_CHUNK_ROWS = 400;

export const chunked = <T>(items: readonly T[], size = INSERT_CHUNK_ROWS): T[][] => {
  const out: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    out.push(items.slice(index, index + size));
  }
  return out;
};
