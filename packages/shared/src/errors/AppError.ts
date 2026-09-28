import type { ErrorCode } from './codes.js';
import { ERROR_CODES } from './codes.js';

export interface AppErrorOptions {
  /** HTTP status the error mapper should use. */
  status?: number;
  /** Safe, serialisable extra information. Never put secrets in here. */
  details?: unknown;
  cause?: unknown;
  /** Whether a failed automation job may be attempted again. */
  retryable?: boolean;
}

/**
 * Base class for every error the application raises on purpose.
 * Anything that is not an AppError is treated as an unexpected internal fault.
 */
export class AppError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly details: unknown;
  readonly retryable: boolean;

  constructor(code: ErrorCode, message: string, options: AppErrorOptions = {}) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = new.target.name;
    this.code = code;
    this.status = options.status ?? 500;
    this.details = options.details;
    this.retryable = options.retryable ?? false;
  }

  toJSON(): { code: ErrorCode; message: string; details?: unknown } {
    return this.details === undefined
      ? { code: this.code, message: this.message }
      : { code: this.code, message: this.message, details: this.details };
  }
}

export const isAppError = (value: unknown): value is AppError => value instanceof AppError;

export class ValidationError extends AppError {
  constructor(message: string, details?: unknown) {
    super(ERROR_CODES.VALIDATION_ERROR, message, { status: 400, details });
  }
}
