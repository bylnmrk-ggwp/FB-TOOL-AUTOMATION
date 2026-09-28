import type { z } from 'zod';
import { parseOrThrow } from '@fb/shared';

/**
 * Thin wrappers so controllers read as `const body = validateBody(schema, request)`
 * and never touch an unvalidated `unknown`.
 */
export const validateBody = <T extends z.ZodTypeAny>(
  schema: T,
  request: { body: unknown },
): z.output<T> => parseOrThrow(schema, request.body, 'request body');

export const validateQuery = <T extends z.ZodTypeAny>(
  schema: T,
  request: { query: unknown },
): z.output<T> => parseOrThrow(schema, request.query, 'query string');

export const validateParams = <T extends z.ZodTypeAny>(
  schema: T,
  request: { params: unknown },
): z.output<T> => parseOrThrow(schema, request.params, 'route parameters');
