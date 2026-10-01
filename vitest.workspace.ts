import { defineWorkspace } from 'vitest/config';

/**
 * Workspace packages are loaded as built ESM rather than transformed by Vite:
 * they are ordinary Node code, and inlining them would hide Node built-ins
 * such as `node:sqlite` from the resolver. Tests therefore exercise exactly
 * what the server runs.
 */
const external = {
  server: { deps: { external: [/[\\/]packages[\\/][^\\/]+[\\/]dist[\\/]/] } },
};

/**
 * Two suites with different costs: `unit` is pure and fast, `integration`
 * touches a real SQLite file and a real Fastify instance. End-to-end tests run
 * under Playwright Test instead, from playwright.config.ts.
 */
export default defineWorkspace([
  {
    test: {
      name: 'unit',
      include: ['tests/unit/**/*.test.ts'],
      environment: 'node',
      ...external,
    },
  },
  {
    test: {
      name: 'integration',
      include: ['tests/integration/**/*.test.ts'],
      environment: 'node',
      // Each file opens its own database; one process keeps the temporary
      // files and the SQLite locks predictable.
      pool: 'forks',
      poolOptions: { forks: { singleFork: true } },
      testTimeout: 30_000,
      // Each test boots the whole server; on a loaded machine that alone can
      // pass the default ten seconds.
      hookTimeout: 60_000,
      ...external,
    },
  },
]);
