import type { FastifyInstance } from 'fastify';
import { ZodError } from 'zod';
import { AppError, ERROR_CODES, isAppError, ValidationError } from '@fb/shared';
import type { Logger } from '@fb/application';

const NOT_FOUND = new AppError(ERROR_CODES.NOT_FOUND, 'Route not found', { status: 404 });

/**
 * The single place an error becomes an HTTP response. Anything that is not an
 * AppError is reported as an internal error, and its message is withheld in
 * production so stack details never reach a browser.
 */
export const registerErrorHandler = (
  app: FastifyInstance,
  logger: Logger,
  isProduction: boolean,
): void => {
  app.setNotFoundHandler((request, reply) => {
    void reply.status(NOT_FOUND.status).send({
      error: { code: NOT_FOUND.code, message: `${request.method} ${request.url} is not a route` },
    });
  });

  app.setErrorHandler((error, request, reply) => {
    const normalised = toAppError(error);
    const context = {
      requestId: request.requestId,
      method: request.method,
      url: request.url,
      code: normalised.code,
    };

    if (normalised.status >= 500) {
      const stack = error instanceof Error ? error.stack : undefined;
      logger.error(normalised.message, { ...context, stack });
    } else {
      logger.warn(normalised.message, context);
    }

    const body =
      normalised.status >= 500 && isProduction
        ? { error: { code: normalised.code, message: 'Internal server error' } }
        : { error: normalised.toJSON() };

    void reply.status(normalised.status).send(body);
  });
};

const toAppError = (error: unknown): AppError => {
  if (isAppError(error)) return error;

  if (error instanceof ZodError) {
    return new ValidationError('Invalid request', error.flatten());
  }

  // Fastify raises these for malformed bodies and unsupported media types.
  if (typeof error === 'object' && error !== null && 'statusCode' in error) {
    const status = Number((error as { statusCode?: unknown }).statusCode);
    const message = error instanceof Error ? error.message : 'Request failed';
    if (Number.isInteger(status) && status >= 400 && status < 500) {
      return new AppError(ERROR_CODES.VALIDATION_ERROR, message, { status });
    }
  }

  return new AppError(
    ERROR_CODES.INTERNAL_ERROR,
    error instanceof Error ? error.message : 'Unexpected error',
    { status: 500, cause: error },
  );
};
