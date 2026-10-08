import { join } from 'node:path';
import { buildApp } from './app.js';
import { createContainer } from './bootstrap/container.js';
import { loadConfig, repoRoot } from './config/index.js';

/** Loads .env when there is one. Real environment variables still win. */
const loadEnvFile = (): void => {
  try {
    process.loadEnvFile(join(repoRoot(), '.env'));
  } catch {
    // No .env file: the defaults in config/env.ts apply.
  }
};

const main = async (): Promise<void> => {
  loadEnvFile();
  const config = loadConfig();
  const container = createContainer(config);
  if (config.auth.password === null) {
    container.logger.warn('API has no login; keep it on 127.0.0.1 and do not expose it', {
      event: 'auth.disabled',
    });
  } else if (config.auth.secretSource === 'generated') {
    container.logger.warn('AUTH_SECRET is unset; every device is logged out at each restart', {
      event: 'auth.secret_generated',
    });
  }
  await container.start();
  const app = await buildApp(container);

  const close = async (signal: string): Promise<void> => {
    container.logger.info(`Received ${signal}, shutting down`, { event: 'server.stopping' });
    await app.close();
    await container.shutdown();
    process.exit(0);
  };

  for (const signal of ['SIGINT', 'SIGTERM'] as const) {
    process.once(signal, () => {
      void close(signal);
    });
  }

  await app.listen({ host: config.host, port: config.port });
  container.logger.info(`API listening on http://${config.host}:${config.port}`, {
    event: 'server.started',
    env: config.env,
  });
};

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exit(1);
});
