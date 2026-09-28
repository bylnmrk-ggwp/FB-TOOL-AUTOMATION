import type { FastifyInstance } from 'fastify';
import type { GroupController, OperatorInputController } from '../controllers/GroupController.js';

export const groupRoutes =
  (groups: GroupController, operator: OperatorInputController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/groups', groups.list);
    app.get('/groups/summary', groups.summaries);
    app.post('/groups/fetch', groups.fetch);

    app.get('/input', operator.list);
    app.post('/input', operator.answer);
  };
