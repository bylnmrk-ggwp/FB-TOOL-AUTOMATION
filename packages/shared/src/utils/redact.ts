const SECRET_KEY = /pass(word)?|cookie|token|secret|authorization|session|credential/i;
const REDACTED = '[redacted]';

/**
 * Removes credential-shaped values before anything reaches a log sink.
 * Applied at the logger boundary so callers cannot forget it.
 */
export const redact = (value: unknown, depth = 0): unknown => {
  if (depth > 6 || value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map((item) => redact(item, depth + 1));

  const output: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
    output[key] = SECRET_KEY.test(key) ? REDACTED : redact(entry, depth + 1);
  }
  return output;
};
