import type { FastifyInstance } from 'fastify';
import type { AccountController } from '../controllers/AccountController.js';

export const accountRoutes =
  (controller: AccountController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/accounts', controller.list);
    app.post('/accounts', controller.create);

    // Declared before `/accounts/:id` so the literal segments win the match.
    app.post('/accounts/import', controller.import);
    app.get('/accounts/export', controller.export);

    app.get('/accounts/:id', controller.get);
    app.patch('/accounts/:id', controller.update);
    app.delete('/accounts/:id', controller.remove);
    app.post('/accounts/:id/enable', controller.enable);
    app.post('/accounts/:id/disable', controller.disable);
  };
