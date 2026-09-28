import { defineConfig, devices } from '@playwright/test';

const WEB_PORT = 5174;
const API_PORT = 3101;
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;

/**
 * End-to-end means the real React build talking to the real API over HTTP,
 * against a real SQLite file. Only the automation target is out of scope: a
 * test must never post to Facebook, so these tests stop short of running a job.
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env['CI'] === undefined ? 0 : 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env['CI'] === undefined ? 'list' : [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: WEB_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: [
    {
      command: 'node apps/server/dist/main.js',
      url: `http://127.0.0.1:${API_PORT}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        NODE_ENV: 'test',
        HOST: '127.0.0.1',
        PORT: String(API_PORT),
        LOG_LEVEL: 'warn',
        CORS_ORIGIN: WEB_URL,
        // A directory of its own, so an end-to-end run never touches the
        // database somebody is developing against.
        DATABASE_FILE: './data/e2e/database/e2e.sqlite',
        PROFILE_DIR: './data/e2e/browser-profiles',
        UPLOAD_DIR: './data/e2e/uploads',
        EXPORT_DIR: './data/e2e/exports',
        IMPORT_DIR: './data/e2e/imports',
        LOG_DIR: './data/e2e/logs',
        BROWSER_HEADLESS: 'true',
      },
    },
    {
      command: `pnpm --filter @fb/web dev`,
      url: WEB_URL,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        VITE_PORT: String(WEB_PORT),
        VITE_API_URL: `http://127.0.0.1:${API_PORT}`,
      },
    },
  ],
});
