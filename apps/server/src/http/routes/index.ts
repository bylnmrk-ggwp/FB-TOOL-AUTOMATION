import type { FastifyInstance } from 'fastify';
import { API_PREFIX } from '@fb/shared';
import type { Container } from '../../bootstrap/container.js';
import { HealthController } from '../controllers/HealthController.js';
import { healthRoutes } from './health.routes.js';

/** Mounts every versioned route group under a single prefix. */
export const registerRoutes = async (app: FastifyInstance, container: Container): Promise<void> => {
  const health = new HealthController(container.health);

  await app.register(
    async (api) => {
      await api.register(healthRoutes(health));
    },
    { prefix: API_PREFIX },
  );
};
