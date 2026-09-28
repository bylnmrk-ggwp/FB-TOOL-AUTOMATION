import type { FastifyReply, FastifyRequest } from 'fastify';
import type { HealthService } from '../../modules/health/HealthService.js';

/** Controllers stay this thin: call one service, shape one response. */
export class HealthController {
  constructor(private readonly health: HealthService) {}

  get = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const result = await this.health.check();
    await reply.status(result.status === 'ok' ? 200 : 503).send(result);
  };
}
