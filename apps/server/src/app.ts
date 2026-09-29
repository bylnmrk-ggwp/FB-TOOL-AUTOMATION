import { existsSync } from 'node:fs';
import { join } from 'node:path';
import Fastify, { type FastifyInstance } from 'fastify';
import cors from '@fastify/cors';
import multipart from '@fastify/multipart';
import fastifyStatic from '@fastify/static';
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
  await serveWebApp(app, container.config.paths.webDist);

  return app;
};

/**
 * The built control panel, from the same process and port as the API, so a
 * service install is one process at one address. Skipped when there is no
 * build — in development Vite serves the app and proxies /api here.
 *
 * The app routes on the client, so any GET that is not an API call and not a
 * file gets index.html; unknown API paths keep their JSON 404.
 */
const serveWebApp = async (app: FastifyInstance, webDist: string): Promise<void> => {
  if (!existsSync(join(webDist, 'index.html'))) return;

  await app.register(fastifyStatic, { root: webDist, prefix: '/', wildcard: false });
  app.get('/*', (request, reply) => {
    if (request.url.startsWith('/api/') || request.url.startsWith('/ws')) {
      return reply.callNotFound();
    }
    return reply.sendFile('index.html');
  });
};
