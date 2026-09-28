import type { FastifyReply, FastifyRequest } from 'fastify';
import {
  ListLogsQuerySchema,
  SettingsInvalidError,
  UpdateSettingsSchema,
  validateSettings,
  type MediaRef,
} from '@fb/shared';
import type { FileStore, Repositories } from '@fb/application';
import type { AppConfig } from '../../config/index.js';
import type { DashboardService } from '../../modules/monitoring/DashboardService.js';
import { validateBody, validateQuery } from '../middleware/validate.js';

export interface SystemControllerDeps {
  repositories: Repositories;
  dashboard: DashboardService;
  files: FileStore;
  config: AppConfig;
  /** Applied as soon as the concurrency setting changes. */
  onSettingsChanged: (concurrency: number) => void;
}

/** Logs, settings, dashboard and uploads: the reads the shell of the UI needs. */
export class SystemController {
  constructor(private readonly deps: SystemControllerDeps) {}

  logs = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const query = validateQuery(ListLogsQuerySchema, request);
    const page = await this.deps.repositories.logs.list({
      limit: query.limit,
      offset: query.offset,
      ...(query.level === undefined ? {} : { level: query.level }),
      ...(query.accountId === undefined ? {} : { accountId: query.accountId }),
      ...(query.jobId === undefined ? {} : { jobId: query.jobId }),
      ...(query.event === undefined ? {} : { event: query.event }),
      ...(query.search === undefined ? {} : { search: query.search }),
      ...(query.from === undefined ? {} : { from: new Date(query.from) }),
      ...(query.to === undefined ? {} : { to: new Date(query.to) }),
    });
    await reply.send(page);
  };

  dashboard = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send(await this.deps.dashboard.stats());
  };

  readSettings = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send(await this.deps.repositories.settings.read());
  };

  updateSettings = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const patch = validateBody(UpdateSettingsSchema, request);
    const current = await this.deps.repositories.settings.read();

    // Cross-field rules a per-field PATCH cannot express are checked against
    // the settings as they would be after the change.
    const problems = validateSettings({ ...current, ...patch });
    if (problems.length > 0) throw new SettingsInvalidError(problems);

    const updated = await this.deps.repositories.settings.write(patch);
    this.deps.onSettingsChanged(updated.globalConcurrency);
    await reply.send(updated);
  };

  /** Read-only: the frontend can see where things live but never move them. */
  paths = async (_request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    await reply.send({
      profileDir: this.deps.config.paths.profileDir,
      uploadDir: this.deps.config.paths.uploadDir,
      exportDir: this.deps.config.paths.exportDir,
      importDir: this.deps.config.paths.importDir,
      logDir: this.deps.config.paths.logDir,
      databaseFile: this.deps.config.paths.databaseFile,
    });
  };

  upload = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const file = await request.file();
    if (file === undefined) {
      await reply.status(400).send({
        error: { code: 'VALIDATION_ERROR', message: 'Send one file as multipart/form-data' },
      });
      return;
    }

    const buffer = await file.toBuffer();
    const stored = await this.deps.files.save(file.filename, file.mimetype, buffer);

    const media: MediaRef = {
      id: stored.id,
      fileName: stored.fileName,
      mimeType: stored.mimeType,
      sizeBytes: stored.sizeBytes,
    };
    await reply.status(201).send(media);
  };
}
