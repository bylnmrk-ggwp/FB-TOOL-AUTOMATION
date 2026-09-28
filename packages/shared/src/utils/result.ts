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
  throw new ValidationError(`Invalid ${what}: ${firstIssue(result.error)}`, result.error.flatten());
};

/**
 * The first problem, named: "accountIds: Array must contain at most 5000
 * element(s)". A person fixing a request needs the field, not just the word
 * "invalid".
 */
export const firstIssue = (error: z.ZodError): string => {
  const issue = error.issues[0];
  if (issue === undefined) return 'no detail';
  const path = issue.path.map(String).join('.');
  return path === '' ? issue.message : `${path}: ${issue.message}`;
};

export const safeJsonParse = (value: string): unknown => {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return undefined;
  }
};
