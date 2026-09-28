import type { FastifyReply, FastifyRequest } from 'fastify';
import { z } from 'zod';
import {
  AccountIdsSchema,
  CreateAccountSchema,
  IdParamSchema,
  ImportAccountsSchema,
  ListAccountsQuerySchema,
  StorageStateSchema,
  UpdateAccountSchema,
  WorkbookInvalidError,
} from '@fb/shared';
import type { AccountService, JobService, RosterService, SessionService } from '@fb/application';
import { CsvSource } from '../../modules/roster/CsvSource.js';
import type { GoogleSheetsSource } from '../../modules/roster/GoogleSheetsSource.js';
import { validateBody, validateParams, validateQuery } from '../middleware/validate.js';

export interface AccountControllerDeps {
  accounts: AccountService;
  jobs: JobService;
  roster: RosterService;
  rosterSheet: GoogleSheetsSource;
  sessions: SessionService;
}

const LoginBodySchema = AccountIdsSchema.extend({
  waitForOperator: z.boolean().default(true),
});

const CsvBodySchema = z.object({ csv: z.string().min(1).max(2_000_000) });

/**
 * Validate, delegate, respond. No business rule lives here: everything this
 * class knows is how an HTTP request maps onto one use case.
 */
export class AccountController {
  constructor(private readonly deps: AccountControllerDeps) {}

  list = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const query = validateQuery(ListAccountsQuerySchema, request);
    const page = await this.deps.accounts.list({
      limit: query.limit,
      offset: query.offset,
      ...(query.search === undefined ? {} : { search: query.search }),
      ...(query.status === undefined ? {} : { status: query.status }),
      ...(query.loginStatus === undefined ? {} : { loginStatus: query.loginStatus }),
      ...(query.enabled === undefined ? {} : { enabled: query.enabled }),
    });
    await reply.send(page);
  };

  get = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.deps.accounts.get(id));
  };

  create = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(CreateAccountSchema, request);
    await reply.status(201).send(await this.deps.accounts.create(input));
  };

  update = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    const patch = validateBody(UpdateAccountSchema, request);
    await reply.send(await this.deps.accounts.update(id, patch));
  };

  remove = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await this.deps.accounts.delete(id);
    await reply.status(204).send();
  };

  enable = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.deps.accounts.setEnabled(id, true));
  };

  disable = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.deps.accounts.setEnabled(id, false));
  };

  import = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(ImportAccountsSchema, request);
    await reply.send(await this.deps.accounts.import(input.accounts, input.upsert));
  };

  /** Pulls the roster from the configured Google Sheet. */
  importSheet = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send(await this.deps.roster.importFrom(this.deps.rosterSheet));
  };

  /** The same import from a CSV the operator pasted or uploaded. */
  importCsv = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { csv } = validateBody(CsvBodySchema, request);
    await reply.send(await this.deps.roster.importFrom(new CsvSource(csv, 'pasted CSV')));
  };

  export = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    // Export is capped rather than streamed: a few hundred accounts is the
    // scale this system is built for. Passwords are not part of it.
    const page = await this.deps.accounts.list({ limit: 500, offset: 0 });
    await reply
      .header('content-disposition', 'attachment; filename="accounts.json"')
      .send({ exportedAt: new Date().toISOString(), accounts: page.items });
  };

  // --- Login and login checks, as queued jobs ------------------------------

  login = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const body = validateBody(LoginBodySchema, request);
    const jobs = await this.deps.jobs.createBatch({
      accountIds: body.accountIds,
      action: { type: 'login', waitForOperator: body.waitForOperator },
      priority: 10,
    });
    await reply.status(202).send({ jobs });
  };

  checkLogin = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const body = validateBody(AccountIdsSchema, request);
    const jobs = await this.deps.jobs.createBatch({
      accountIds: body.accountIds,
      action: { type: 'check_login' },
      priority: 10,
    });
    await reply.status(202).send({ jobs });
  };

  // --- Sessions -------------------------------------------------------------

  exportSession = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    const session = await this.deps.sessions.export(id);
    await reply
      .header('content-disposition', `attachment; filename="session-${session.accountName}.json"`)
      .send(session);
  };

  importSession = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    const body = request.body as { state?: unknown } | null;
    const parsed = StorageStateSchema.safeParse(body?.state ?? body);
    if (!parsed.success)
      throw new WorkbookInvalidError('the session file is not Playwright storage state');
    await this.deps.sessions.import(id, parsed.data);
    await reply.status(204).send();
  };
}
