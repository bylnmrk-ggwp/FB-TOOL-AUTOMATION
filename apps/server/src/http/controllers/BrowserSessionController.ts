import type { FastifyReply, FastifyRequest } from 'fastify';
import { AppError, ERROR_CODES, IdParamSchema, StartBrowserSchema } from '@fb/shared';
import type { BrowserService } from '@fb/application';
import { validateBody, validateParams } from '../middleware/validate.js';

export class BrowserSessionController {
  constructor(private readonly browsers: BrowserService) {}

  /**
   * 202: the browser is up, but the profile may still be restoring tabs, so
   * the caller should watch the WebSocket rather than assume it is idle.
   */
  start = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    const body = validateBody(StartBrowserSchema, {
      body: request.body === undefined || request.body === null ? {} : request.body,
    });

    const session = await this.browsers.start(id, body.headless);
    await reply.status(202).send(session);
  };

  stop = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await this.browsers.stop(id);
    await reply.status(204).send();
  };

  get = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    const session = this.browsers.get(id);
    // A missing session is a missing resource here, not a conflict.
    if (session === null) {
      throw new AppError(ERROR_CODES.BROWSER_NOT_RUNNING, `No browser is running for ${id}`, {
        status: 404,
        details: { accountId: id },
      });
    }
    await reply.send(session);
  };

  list = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send({ sessions: this.browsers.list() });
  };

  /**
   * A live thumbnail of the account's page. 404 when no browser is running,
   * so the grid can drop a tile the moment its session ends. Not cached: the
   * point is that it changes. The 404 is sent directly rather than thrown:
   * the grid polls every open tile, so a browser that just closed would
   * otherwise fill the log with warnings about an expected miss.
   */
  screenshot = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    const image = await this.browsers.screenshot(id);
    if (image === null) {
      await reply.status(404).send({
        error: {
          code: ERROR_CODES.BROWSER_NOT_RUNNING,
          message: `No browser is running for ${id}`,
          details: { accountId: id },
        },
      });
      return;
    }
    await reply.header('cache-control', 'no-store').type('image/jpeg').send(Buffer.from(image));
  };
}
