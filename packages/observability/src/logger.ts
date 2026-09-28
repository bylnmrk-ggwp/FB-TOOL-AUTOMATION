import { pino, type Logger as PinoLogger, type TransportTargetOptions } from 'pino';
import type { LogContext, Logger } from '@fb/application';
import { redact } from '@fb/shared';

export interface LoggerOptions {
  level: string;
  pretty: boolean;
  /** Written next to the console output so a crash leaves a trace on disk. */
  filePath?: string;
}

const toRecord = (context: LogContext | undefined): Record<string, unknown> =>
  context === undefined ? {} : (redact(context) as Record<string, unknown>);

class PinoAdapter implements Logger {
  constructor(private readonly inner: PinoLogger) {}

  debug(message: string, context?: LogContext): void {
    this.inner.debug(toRecord(context), message);
  }

  info(message: string, context?: LogContext): void {
    this.inner.info(toRecord(context), message);
  }

  warn(message: string, context?: LogContext): void {
    this.inner.warn(toRecord(context), message);
  }

  error(message: string, context?: LogContext): void {
    this.inner.error(toRecord(context), message);
  }

  child(context: LogContext): Logger {
    return new PinoAdapter(this.inner.child(toRecord(context)));
  }
}

export const createLogger = (options: LoggerOptions): Logger => {
  const targets: TransportTargetOptions[] = [
    options.pretty
      ? {
          target: 'pino-pretty',
          options: { colorize: true, translateTime: 'HH:MM:ss.l' },
          level: options.level,
        }
      : { target: 'pino/file', options: { destination: 1 }, level: options.level },
  ];

  if (options.filePath !== undefined) {
    targets.push({
      target: 'pino/file',
      options: { destination: options.filePath, mkdir: true },
      level: options.level,
    });
  }

  return new PinoAdapter(
    pino({
      level: options.level,
      // A second guard behind redact(): pino strips these even if a caller
      // hands us an object we did not build.
      redact: {
        paths: ['password', 'cookie', 'cookies', 'token', 'authorization', 'sessionToken'],
        censor: '[redacted]',
      },
      transport: { targets },
    }),
  );
};

/** Logger used by tests and scripts that should stay silent. */
export const createSilentLogger = (): Logger => new PinoAdapter(pino({ level: 'silent' }));
