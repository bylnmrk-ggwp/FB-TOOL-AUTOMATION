import { createId, nowIso, redact, type LogLevel } from '@fb/shared';
import type { LogRepository } from '@fb/domain';
import type { EventPublisher, LogContext, Logger } from '@fb/application';

/**
 * Wraps a console logger so that everything also reaches the database and the
 * WebSocket stream. The Logs page and the live feed are then the same data the
 * server logged, not a second, drifting copy.
 *
 * Persistence is fire-and-forget on purpose: a failing log write must never
 * fail the operation that produced it.
 */
export class PersistentLogger implements Logger {
  constructor(
    private readonly inner: Logger,
    private readonly repository: LogRepository,
    private readonly events: EventPublisher,
    private readonly base: LogContext = {},
    /** Debug lines stay in the console; storing them would bury the rest. */
    private readonly persistFrom: LogLevel = 'info',
  ) {}

  debug(message: string, context?: LogContext): void {
    this.write('debug', message, context);
  }

  info(message: string, context?: LogContext): void {
    this.write('info', message, context);
  }

  warn(message: string, context?: LogContext): void {
    this.write('warn', message, context);
  }

  error(message: string, context?: LogContext): void {
    this.write('error', message, context);
  }

  child(context: LogContext): Logger {
    return new PersistentLogger(
      this.inner.child(context),
      this.repository,
      this.events,
      { ...this.base, ...context },
      this.persistFrom,
    );
  }

  private write(level: LogLevel, message: string, context?: LogContext): void {
    this.inner[level](message, context);

    const order: LogLevel[] = ['debug', 'info', 'warn', 'error'];
    if (order.indexOf(level) < order.indexOf(this.persistFrom)) return;

    const merged = { ...this.base, ...context };
    const { requestId, accountId, jobId, sessionId, event, ...rest } = merged;

    void this.repository
      .append({
        id: createId('log'),
        level,
        message,
        event: typeof event === 'string' ? event : null,
        accountId: typeof accountId === 'string' ? accountId : null,
        jobId: typeof jobId === 'string' ? jobId : null,
        sessionId: typeof sessionId === 'string' ? sessionId : null,
        requestId: typeof requestId === 'string' ? requestId : null,
        context: Object.keys(rest).length === 0 ? null : (redact(rest) as Record<string, unknown>),
      })
      .then((entry) => {
        this.events.publish({ type: 'log.created', timestamp: nowIso(), payload: entry });
      })
      .catch((error: unknown) => {
        this.inner.error('Could not persist a log entry', {
          event: 'log.persist_failed',
          reason: error instanceof Error ? error.message : String(error),
        });
      });
  }
}
