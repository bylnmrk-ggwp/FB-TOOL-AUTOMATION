import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '@fb/server/app';
import { createContainer, type Container } from '@fb/server/container';
import type { AppConfig } from '@fb/server/config';
import { DEFAULTS, type ServerEvent } from '@fb/shared';
import { FakeBrowserController } from './fake-browser';

export interface TestServer {
  app: FastifyInstance;
  container: Container;
  browser: FakeBrowserController;
  events: ServerEvent[];
  directory: string;
  dispose: () => Promise<void>;
}

/** Config pointing at a throwaway directory, otherwise identical to production. */
export const testConfig = (directory: string): AppConfig => ({
  env: 'test',
  isProduction: false,
  host: '127.0.0.1',
  port: 0,
  logLevel: 'error',
  corsOrigins: ['http://localhost:5173'],
  paths: {
    databaseFile: join(directory, 'database', 'test.sqlite'),
    profileDir: join(directory, 'browser-profiles'),
    uploadDir: join(directory, 'uploads'),
    exportDir: join(directory, 'exports'),
    importDir: join(directory, 'imports'),
    logDir: join(directory, 'logs'),
  },
  browser: { executablePath: null, channel: 'chromium', headless: true },
  queue: {
    globalConcurrency: 2,
    defaultTimeoutMs: 5_000,
    defaultMaxRetries: DEFAULTS.maxRetries,
    staleJobTimeoutMs: DEFAULTS.staleJobTimeoutMs,
    profileLockTtlMs: DEFAULTS.profileLockTtlMs,
  },
});

/**
 * Boots the real application — same container, same routes, same database
 * engine — against a temporary directory, and drives it through `app.inject`
 * so no port is bound.
 */
export const createTestServer = async (): Promise<TestServer> => {
  const directory = mkdtempSync(join(tmpdir(), 'fb-automation-server-'));
  const browser = new FakeBrowserController();
  const container = createContainer(testConfig(directory), { browserController: browser });
  await container.start();
  const app = await buildApp(container);
  await app.ready();

  // Every published event is captured so tests can assert on what the UI would
  // have been told.
  const events: ServerEvent[] = [];
  container.events.subscribe((event) => events.push(event));

  return {
    app,
    container,
    browser,
    events,
    directory,
    dispose: async () => {
      await app.close();
      await container.shutdown();
      rmSync(directory, { recursive: true, force: true });
    },
  };
};
