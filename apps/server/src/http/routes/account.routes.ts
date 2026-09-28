import type { FastifyInstance } from 'fastify';
import type { AccountController } from '../controllers/AccountController.js';

export const accountRoutes =
  (controller: AccountController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/accounts', controller.list);
    app.post('/accounts', controller.create);

    // Declared before `/accounts/:id` so the literal segments win the match.
    app.post('/accounts/import', controller.import);
    app.post('/accounts/import/sheet', controller.importSheet);
    app.post('/accounts/import/csv', controller.importCsv);
    app.get('/accounts/export', controller.export);
    app.post('/accounts/login', controller.login);
    app.post('/accounts/check-login', controller.checkLogin);

    app.get('/accounts/:id', controller.get);
    app.patch('/accounts/:id', controller.update);
    app.delete('/accounts/:id', controller.remove);
    app.post('/accounts/:id/enable', controller.enable);
    app.post('/accounts/:id/disable', controller.disable);
    app.get('/accounts/:id/session', controller.exportSession);
    app.post('/accounts/:id/session', controller.importSession);
  };
