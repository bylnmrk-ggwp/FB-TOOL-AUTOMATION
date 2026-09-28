import type { FastifyInstance } from 'fastify';
import { createId } from '@fb/shared';
import type { Logger } from '@fb/application';

declare module 'fastify' {
  interface FastifyRequest {
    /** Correlates every log line produced while handling this request. */
    requestId: string;
    /** Structured application logger, already bound to the request id. */
    appLog: Logger;
  }
}

export const registerRequestContext = (app: FastifyInstance, logger: Logger): void => {
  app.decorateRequest('requestId', '');
  app.decorateRequest('appLog', null as unknown as Logger);

  app.addHook('onRequest', (request, reply, done) => {
    const header = request.headers['x-request-id'];
    const requestId = typeof header === 'string' && header.length > 0 ? header : createId('req');
    request.requestId = requestId;
    request.appLog = logger.child({ requestId });
    void reply.header('x-request-id', requestId);
    done();
  });
};
