import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '@fb/server/app';
import { createContainer, type Container } from '@fb/server/container';
import type { AppConfig } from '@fb/server/config';
import { DEFAULTS } from '@fb/shared';

export interface TestServer {
  app: FastifyInstance;
  container: Container;
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
  const container = createContainer(testConfig(directory));
  await container.start();
  const app = await buildApp(container);
  await app.ready();

  return {
    app,
    container,
    directory,
    dispose: async () => {
      await app.close();
      await container.shutdown();
      rmSync(directory, { recursive: true, force: true });
    },
  };
};
