export interface LogContext {
  requestId?: string;
  accountId?: string;
  jobId?: string;
  sessionId?: string;
  event?: string;
  [key: string]: unknown;
}

/**
 * Structured logging only. Implementations redact credential-shaped fields
 * before anything is written, so callers cannot leak a cookie by accident.
 */
export interface Logger {
  debug(message: string, context?: LogContext): void;
  info(message: string, context?: LogContext): void;
  warn(message: string, context?: LogContext): void;
  error(message: string, context?: LogContext): void;
  /** Returns a logger that merges `context` into every later call. */
  child(context: LogContext): Logger;
}
