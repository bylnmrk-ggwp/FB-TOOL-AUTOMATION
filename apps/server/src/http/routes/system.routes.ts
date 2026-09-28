import type { FastifyInstance } from 'fastify';
import type { SystemController } from '../controllers/SystemController.js';

export const systemRoutes =
  (controller: SystemController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/logs', controller.logs);
    app.get('/dashboard', controller.dashboard);
    app.get('/settings', controller.readSettings);
    app.patch('/settings', controller.updateSettings);
    app.get('/settings/paths', controller.paths);
    app.post('/media', controller.upload);
  };
