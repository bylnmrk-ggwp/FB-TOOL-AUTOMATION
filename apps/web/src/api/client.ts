import type { z } from 'zod';
import { API_PREFIX, ApiErrorSchema, AppError, ERROR_CODES, type ErrorCode } from '@fb/shared';
import { authHeaders, reportUnauthorized } from '../lib/auth';
import { WEB_CONFIG } from '../lib/env';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null | string[]>;
  signal?: AbortSignal;
}

const buildUrl = (path: string, query: RequestOptions['query']): string => {
  const url = `${WEB_CONFIG.apiBaseUrl}${API_PREFIX}${path}`;
  if (query === undefined) return url;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, item);
    } else {
      params.set(key, String(value));
    }
  }
  const search = params.toString();
  return search.length > 0 ? `${url}?${search}` : url;
};

/**
 * The only place the frontend performs network I/O. Responses are validated
 * against the shared schema, so a contract drift fails loudly instead of
 * spreading undefined through the UI.
 */
export const apiRequest = async <T extends z.ZodTypeAny>(
  path: string,
  schema: T,
  options: RequestOptions = {},
): Promise<z.output<T>> => {
  const { method = 'GET', body, query, signal } = options;

  const response = await fetch(buildUrl(path, query), {
    method,
    signal,
    headers: {
      ...authHeaders(),
      ...(body === undefined ? {} : { 'content-type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null);

  if (!response.ok) {
    const parsed = ApiErrorSchema.safeParse(payload);
    // AUTH_INVALID is a wrong password on the login form and stays there;
    // AUTH_REQUIRED means the token is gone and the gate must take over.
    if (
      response.status === 401 &&
      parsed.success &&
      parsed.data.error.code === ERROR_CODES.AUTH_REQUIRED
    ) {
      reportUnauthorized();
    }
    throw parsed.success
      ? new AppError(parsed.data.error.code as ErrorCode, parsed.data.error.message, {
          status: response.status,
          details: parsed.data.error.details,
        })
      : new AppError(ERROR_CODES.INTERNAL_ERROR, `Request failed with ${response.status}`, {
          status: response.status,
        });
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new AppError(ERROR_CODES.VALIDATION_ERROR, `Unexpected response shape for ${path}`, {
      status: 500,
      details: parsed.error.flatten(),
    });
  }
  return parsed.data;
};
