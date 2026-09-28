import type { FastifyInstance } from 'fastify';
import { API_PREFIX } from '@fb/shared';
import type { Container } from '../../bootstrap/container.js';
import { AccountController } from '../controllers/AccountController.js';
import { BrowserSessionController } from '../controllers/BrowserSessionController.js';
import { HealthController } from '../controllers/HealthController.js';
import { JobController } from '../controllers/JobController.js';
import { SystemController } from '../controllers/SystemController.js';
import { accountRoutes } from './account.routes.js';
import { browserRoutes } from './browser.routes.js';
import { healthRoutes } from './health.routes.js';
import { jobRoutes } from './job.routes.js';
import { systemRoutes } from './system.routes.js';

/** Mounts every versioned route group under a single prefix. */
export const registerRoutes = async (app: FastifyInstance, container: Container): Promise<void> => {
  const health = new HealthController(container.health);
  const accounts = new AccountController(container.accounts);
  const browsers = new BrowserSessionController(container.browsers);
  const jobs = new JobController(container.jobs);
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
      await api.register(systemRoutes(system));
    },
    { prefix: API_PREFIX },
  );
};
