import type { FastifyReply, FastifyRequest } from 'fastify';
import {
  CreateAccountSchema,
  IdParamSchema,
  ImportAccountsSchema,
  ListAccountsQuerySchema,
  UpdateAccountSchema,
} from '@fb/shared';
import type { AccountService } from '@fb/application';
import { validateBody, validateParams, validateQuery } from '../middleware/validate.js';

/**
 * Validate, delegate, respond. No business rule lives here: everything this
 * class knows is how an HTTP request maps onto one use case.
 */
export class AccountController {
  constructor(private readonly accounts: AccountService) {}

  list = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const query = validateQuery(ListAccountsQuerySchema, request);
    const page = await this.accounts.list({
      limit: query.limit,
      offset: query.offset,
      ...(query.search === undefined ? {} : { search: query.search }),
      ...(query.status === undefined ? {} : { status: query.status }),
      ...(query.enabled === undefined ? {} : { enabled: query.enabled }),
    });
    await reply.send(page);
  };

  get = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.accounts.get(id));
  };

  create = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(CreateAccountSchema, request);
    const account = await this.accounts.create(input);
    await reply.status(201).send(account);
  };

  update = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    const patch = validateBody(UpdateAccountSchema, request);
    await reply.send(await this.accounts.update(id, patch));
  };

  remove = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await this.accounts.delete(id);
    await reply.status(204).send();
  };

  enable = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.accounts.setEnabled(id, true));
  };

  disable = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.accounts.setEnabled(id, false));
  };

  import = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(ImportAccountsSchema, request);
    await reply.send(await this.accounts.import(input.accounts, input.upsert));
  };

  export = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    // Export is capped rather than streamed: a few hundred accounts is the
    // scale this system is built for, and a single JSON body is easiest to
    // hand to an operator.
    const page = await this.accounts.list({ limit: 500, offset: 0 });
    await reply
      .header('content-disposition', 'attachment; filename="accounts.json"')
      .send({ exportedAt: new Date().toISOString(), accounts: page.items });
  };
}
