import type { FastifyInstance } from 'fastify';
import type { JobController } from '../controllers/JobController.js';

export const jobRoutes =
  (controller: JobController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/jobs', controller.list);
    app.post('/jobs', controller.create);

    // Literal segments before the parameterised one.
    app.post('/jobs/batch', controller.createBatch);
    app.post('/jobs/share-to-groups', controller.shareToGroups);
    app.post('/jobs/join-groups', controller.joinGroups);
    app.post('/jobs/cancel-all', controller.cancelAll);
    app.get('/jobs/stats', controller.stats);

    app.get('/jobs/:id', controller.get);
    app.post('/jobs/:id/cancel', controller.cancel);
    app.post('/jobs/:id/retry', controller.retry);
  };
