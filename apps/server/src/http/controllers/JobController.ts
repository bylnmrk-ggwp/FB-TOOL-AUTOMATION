import type { FastifyReply, FastifyRequest } from 'fastify';
import {
  CreateJobBatchSchema,
  CreateJobSchema,
  IdParamSchema,
  ListJobsQuerySchema,
} from '@fb/shared';
import type { JobService } from '@fb/application';
import { validateBody, validateParams, validateQuery } from '../middleware/validate.js';

export class JobController {
  constructor(private readonly jobs: JobService) {}

  list = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const query = validateQuery(ListJobsQuerySchema, request);
    const page = await this.jobs.list({
      limit: query.limit,
      offset: query.offset,
      ...(query.status === undefined ? {} : { status: query.status }),
      ...(query.accountId === undefined ? {} : { accountId: query.accountId }),
      ...(query.type === undefined ? {} : { type: query.type }),
    });
    await reply.send(page);
  };

  get = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.jobs.get(id));
  };

  create = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(CreateJobSchema, request);
    await reply.status(201).send(await this.jobs.create(input));
  };

  createBatch = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(CreateJobBatchSchema, request);
    await reply.status(201).send({ jobs: await this.jobs.createBatch(input) });
  };

  cancel = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.jobs.cancel(id));
  };

  retry = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.jobs.retry(id));
  };

  stats = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send(await this.jobs.stats());
  };
}
