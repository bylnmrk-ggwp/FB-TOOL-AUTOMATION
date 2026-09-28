import Fastify, { type FastifyInstance } from 'fastify';
import cors from '@fastify/cors';
import multipart from '@fastify/multipart';
import type { Container } from './bootstrap/container.js';
import { registerErrorHandler, registerRequestContext } from './http/middleware/index.js';
import { registerRoutes } from './http/routes/index.js';
import { registerWebSocket } from './websocket/server.js';

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

/**
 * Builds the HTTP application without starting it, so integration tests can
 * drive the real routes through `app.inject`.
 */
export const buildApp = async (container: Container): Promise<FastifyInstance> => {
  const app = Fastify({
    // Application logging goes through @fb/observability; Fastify's own logger
    // would be a second, unstructured channel.
    logger: false,
    bodyLimit: 10 * 1024 * 1024,
    trustProxy: false,
  });

  await app.register(cors, {
    origin: container.config.corsOrigins,
    credentials: true,
    exposedHeaders: ['x-request-id'],
  });

  await app.register(multipart, {
    limits: { fileSize: MAX_UPLOAD_BYTES, files: 1 },
  });

  registerRequestContext(app, container.logger);
  registerErrorHandler(app, container.logger, container.config.isProduction);

  await registerWebSocket(app, container);
  await registerRoutes(app, container);

  return app;
};
