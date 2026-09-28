import type { FastifyInstance } from 'fastify';
import type { BrowserSessionController } from '../controllers/BrowserSessionController.js';

export const browserRoutes =
  (controller: BrowserSessionController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/browser/sessions', controller.list);
    app.post('/accounts/:id/browser/start', controller.start);
    app.post('/accounts/:id/browser/stop', controller.stop);
    app.get('/accounts/:id/browser', controller.get);
  };
