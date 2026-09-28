import type { FastifyReply, FastifyRequest } from 'fastify';
import { AccountIdsSchema, AnswerOperatorRequestSchema, ListGroupsQuerySchema } from '@fb/shared';
import type { GroupService, JobService, OperatorInputService } from '@fb/application';
import { validateBody, validateQuery } from '../middleware/validate.js';

/** Groups, and the operator prompts that pause a job — both small, both read-mostly. */
export class GroupController {
  constructor(
    private readonly groups: GroupService,
    private readonly jobs: JobService,
  ) {}

  list = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const query = validateQuery(ListGroupsQuerySchema, request);
    await reply.send(
      await this.groups.list({
        limit: query.limit,
        offset: query.offset,
        ...(query.accountId === undefined ? {} : { accountId: query.accountId }),
        ...(query.search === undefined ? {} : { search: query.search }),
      }),
    );
  };

  summaries = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send({ groups: await this.groups.summaries() });
  };

  /** Queues a fetch for each account; the lists update as the jobs finish. */
  fetch = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const body = validateBody(AccountIdsSchema, request);
    const jobs = await this.jobs.createBatch({
      accountIds: body.accountIds,
      action: { type: 'fetch_groups' },
      priority: 5,
    });
    await reply.status(202).send({ jobs });
  };
}

export class OperatorInputController {
  constructor(private readonly operator: OperatorInputService) {}

  list = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send({ requests: this.operator.list() });
  };

  answer = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const body = validateBody(AnswerOperatorRequestSchema, request);
    this.operator.answer(body.requestId, body.value, body.cancel);
    await reply.status(204).send();
  };
}
