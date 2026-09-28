import type { z } from 'zod';
import { ValidationError } from '../errors/AppError.js';

/**
 * Parses untrusted input and raises a ValidationError the HTTP layer already
 * knows how to map, instead of leaking a raw ZodError.
 */
export const parseOrThrow = <T extends z.ZodTypeAny>(
  schema: T,
  value: unknown,
  what = 'payload',
): z.output<T> => {
  const result = schema.safeParse(value);
  if (result.success) return result.data;
  throw new ValidationError(`Invalid ${what}`, result.error.flatten());
};

export const safeJsonParse = (value: string): unknown => {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return undefined;
  }
};
