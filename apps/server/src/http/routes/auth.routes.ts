import type { FastifyInstance } from 'fastify';
import type { AuthController } from '../controllers/AuthController.js';

export const authRoutes =
  (controller: AuthController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/auth/session', controller.session);
    app.post('/auth/login', controller.login);
  };
