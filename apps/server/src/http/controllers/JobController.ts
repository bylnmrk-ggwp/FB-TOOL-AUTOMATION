import type { FastifyReply, FastifyRequest } from 'fastify';
import { z } from 'zod';
import {
  CreateJobBatchSchema,
  CreateJobSchema,
  FacebookUrlSchema,
  IdParamSchema,
  IdSchema,
  IsoDateTimeSchema,
  ListJobsQuerySchema,
  PRIORITY_RANGE,
  ReactionTypeSchema,
} from '@fb/shared';
import type { JobService } from '@fb/application';
import { validateBody, validateParams, validateQuery } from '../middleware/validate.js';

const priority = z.number().int().min(PRIORITY_RANGE.min).max(PRIORITY_RANGE.max).default(0);

const ShareToGroupsSchema = z.object({
  accountIds: z.array(IdSchema).min(1).max(500),
  postUrl: FacebookUrlSchema,
  groups: z
    .array(
      z.object({
        name: z.string().trim().min(1).max(200),
        url: FacebookUrlSchema.nullable().default(null),
      }),
    )
    .min(1)
    .max(200),
  comments: z.array(z.string().trim().min(1).max(8_000)).max(50).default([]),
  reaction: ReactionTypeSchema.nullable().default(null),
  shareToTimeline: z.boolean().default(false),
  skipDone: z.boolean().default(true),
  priority,
});

const CommentPostSchema = z.object({
  accountIds: z.array(IdSchema).min(1).max(5000),
  postUrl: FacebookUrlSchema,
  comments: z.array(z.string().trim().min(1).max(8_000)).min(1).max(5000),
  then: z.enum(['none', 'react', 'timeline', 'story']).default('none'),
  reaction: ReactionTypeSchema.nullable().default(null),
  skipDone: z.boolean().default(true),
  priority,
  scheduledFor: IsoDateTimeSchema.optional(),
});

const JoinGroupsSchema = z.object({
  accountIds: z.array(IdSchema).min(1).max(500),
  groupUrls: z.array(FacebookUrlSchema).min(1).max(200),
  skipDone: z.boolean().default(true),
  priority,
});

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

  shareToGroups = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(ShareToGroupsSchema, request);
    const jobs = await this.jobs.createShareToGroups(input);
    await reply.status(201).send({ jobs });
  };

  commentPost = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(CommentPostSchema, request);
    const jobs = await this.jobs.createCommentPost(input);
    await reply.status(201).send({ jobs });
  };

  joinGroups = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const input = validateBody(JoinGroupsSchema, request);
    const jobs = await this.jobs.createJoinGroups(input);
    await reply.status(201).send({ jobs });
  };

  cancel = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.jobs.cancel(id));
  };

  cancelAll = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send({ cancelled: await this.jobs.cancelAll() });
  };

  retry = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { id } = validateParams(IdParamSchema, request);
    await reply.send(await this.jobs.retry(id));
  };

  stats = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send(await this.jobs.stats());
  };
}
