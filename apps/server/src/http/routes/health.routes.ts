import type { FastifyInstance } from 'fastify';
import type { HealthController } from '../controllers/HealthController.js';

export const healthRoutes =
  (controller: HealthController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/health', controller.get);
  };
