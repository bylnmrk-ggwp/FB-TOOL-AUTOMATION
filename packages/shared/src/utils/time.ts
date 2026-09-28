export const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/** Exponential backoff with full jitter, clamped to `maxMs`. */
export const backoffDelayMs = (attempt: number, baseMs: number, maxMs: number): number => {
  const exponential = Math.min(maxMs, baseMs * 2 ** Math.max(0, attempt - 1));
  return Math.round(exponential / 2 + Math.random() * (exponential / 2));
};

/** Uniformly random pause used to keep automation from looking machine-timed. */
export const randomDelayMs = (minMs: number, maxMs: number): number =>
  minMs >= maxMs ? minMs : minMs + Math.floor(Math.random() * (maxMs - minMs + 1));

export const nowIso = (): string => new Date().toISOString();
