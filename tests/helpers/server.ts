import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '@fb/server/app';
import { createContainer, type Container } from '@fb/server/container';
import type { AppConfig } from '@fb/server/config';
import { DEFAULTS, type ServerEvent } from '@fb/shared';
import { FakeBrowserController } from './fake-browser';
import { FakeGateway } from './fake-gateway';

export interface TestServer {
  app: FastifyInstance;
  container: Container;
  browser: FakeBrowserController;
  gateway: FakeGateway;
  events: ServerEvent[];
  directory: string;
  /** Pass true to keep the directory, for a test that restarts the server. */
  dispose: (keepFiles?: boolean) => Promise<void>;
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
  sheets: {
    keyFile: join(directory, 'missing-service-account.json'),
    sheetId: 'test-sheet',
    tab: 'Sheet1',
  },
});

/**
 * Boots the real application — same container, same routes, same database
 * engine — against a temporary directory, and drives it through `app.inject`
 * so no port is bound.
 */
export interface TestServerOptions {
  /** Reuse a directory to simulate a restart against the same database. */
  directory?: string;
  gateway?: FakeGateway;
  /** Leave the queue stopped for tests that drive recovery by hand. */
  autoStartQueue?: boolean;
  concurrency?: number;
}

export const createTestServer = async (options: TestServerOptions = {}): Promise<TestServer> => {
  const directory = options.directory ?? mkdtempSync(join(tmpdir(), 'fb-automation-server-'));
  const browser = new FakeBrowserController();
  const gateway = options.gateway ?? new FakeGateway();

  const config = testConfig(directory);
  if (options.concurrency !== undefined) config.queue.globalConcurrency = options.concurrency;

  const container = createContainer(config, {
    browserController: browser,
    gateway,
    ...(options.autoStartQueue === undefined ? {} : { autoStartQueue: options.autoStartQueue }),
  });
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
    gateway,
    events,
    directory,
    dispose: async (keepFiles = false) => {
      await app.close();
      await container.shutdown();
      if (!keepFiles) rmSync(directory, { recursive: true, force: true });
    },
  };
};
