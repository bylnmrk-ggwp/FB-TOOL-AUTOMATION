/** Empty means same-origin. Anything else is an origin with no trailing slash. */
export const normaliseApiBase = (value: string | undefined): string => {
  const trimmed = (value ?? '').trim();
  return trimmed.replace(/\/+$/, '');
};
