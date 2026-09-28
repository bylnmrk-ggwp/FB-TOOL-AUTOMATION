import type { JobError } from '@fb/shared';
import { isAppError, nowIso } from '@fb/shared';

/**
 * Turns any thrown value into a job error and decides whether another attempt
 * makes sense. Unknown failures are retryable: a crashed browser is far more
 * common than a genuinely impossible action.
 */
export const classifyError = (error: unknown): JobError => {
  if (isAppError(error)) {
    return {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      occurredAt: nowIso(),
    };
  }

  if (error instanceof Error) {
    return {
      code: 'INTERNAL_ERROR',
      message: error.message,
      retryable: true,
      occurredAt: nowIso(),
    };
  }

  return {
    code: 'INTERNAL_ERROR',
    message: String(error),
    retryable: true,
    occurredAt: nowIso(),
  };
};
