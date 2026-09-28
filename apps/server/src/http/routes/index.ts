import type { FastifyInstance } from 'fastify';
import { API_PREFIX } from '@fb/shared';
import type { Container } from '../../bootstrap/container.js';
import { AccountController } from '../controllers/AccountController.js';
import { BrowserSessionController } from '../controllers/BrowserSessionController.js';
import { GroupController, OperatorInputController } from '../controllers/GroupController.js';
import { HealthController } from '../controllers/HealthController.js';
import { JobController } from '../controllers/JobController.js';
import { SystemController } from '../controllers/SystemController.js';
import { accountRoutes } from './account.routes.js';
import { browserRoutes } from './browser.routes.js';
import { groupRoutes } from './group.routes.js';
import { healthRoutes } from './health.routes.js';
import { jobRoutes } from './job.routes.js';
import { systemRoutes } from './system.routes.js';

/** Mounts every versioned route group under a single prefix. */
export const registerRoutes = async (app: FastifyInstance, container: Container): Promise<void> => {
  const health = new HealthController(container.health);
  const accounts = new AccountController({
    accounts: container.accounts,
    jobs: container.jobs,
    roster: container.roster,
    rosterSheet: container.rosterSheet,
    sessions: container.sessions,
  });
  const browsers = new BrowserSessionController(container.browsers);
  const jobs = new JobController(container.jobs);
  const groups = new GroupController(container.groups, container.jobs);
  const operator = new OperatorInputController(container.operator);
  const system = new SystemController({
    repositories: container.repositories,
    dashboard: container.dashboard,
    files: container.files,
    config: container.config,
    onSettingsChanged: (concurrency) => container.queue.setConcurrency(concurrency),
  });

  await app.register(
    async (api) => {
      await api.register(healthRoutes(health));
      await api.register(accountRoutes(accounts));
      await api.register(browserRoutes(browsers));
      await api.register(jobRoutes(jobs));
      await api.register(groupRoutes(groups, operator));
      await api.register(systemRoutes(system));
    },
    { prefix: API_PREFIX },
  );
};
