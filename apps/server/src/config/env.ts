import { randomBytes } from 'node:crypto';
import { z } from 'zod';
import { BROWSER_CHANNELS, DEFAULTS, LOG_LEVELS } from '@fb/shared';
import { resolveFromRoot } from './paths.js';

const booleanish = z
  .union([z.boolean(), z.string()])
  .transform((value) =>
    typeof value === 'boolean' ? value : ['1', 'true', 'yes', 'on'].includes(value.toLowerCase()),
  );

const EnvSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  HOST: z.string().min(1).default('127.0.0.1'),
  PORT: z.coerce.number().int().min(1).max(65_535).default(3001),
  LOG_LEVEL: z.enum(LOG_LEVELS).default('info'),
  CORS_ORIGIN: z.string().default('http://localhost:5173'),

  DATABASE_FILE: z.string().default('./data/database/fb-automation.sqlite'),
  PROFILE_DIR: z.string().default('./data/browser-profiles'),
  UPLOAD_DIR: z.string().default('./data/uploads'),
  EXPORT_DIR: z.string().default('./data/exports'),
  IMPORT_DIR: z.string().default('./data/imports'),
  LOG_DIR: z.string().default('./data/logs'),
  /** The built web app; served by the API when the directory exists. */
  WEB_DIST: z.string().default('./apps/web/dist'),

  BROWSER_EXECUTABLE_PATH: z.string().optional(),
  BROWSER_CHANNEL: z.enum(BROWSER_CHANNELS).default('chromium'),
  BROWSER_HEADLESS: booleanish.default(false),
  GLOBAL_CONCURRENCY: z.coerce.number().int().min(1).max(32).default(DEFAULTS.globalConcurrency),
  DEFAULT_TIMEOUT_MS: z.coerce.number().int().min(1_000).default(DEFAULTS.timeoutMs),
  DEFAULT_MAX_RETRIES: z.coerce.number().int().min(0).max(10).default(DEFAULTS.maxRetries),
  STALE_JOB_TIMEOUT_MS: z.coerce.number().int().min(60_000).default(DEFAULTS.staleJobTimeoutMs),
  PROFILE_LOCK_TTL_MS: z.coerce.number().int().min(30_000).default(DEFAULTS.profileLockTtlMs),

  // The roster Google Sheet. The key file is a service-account JSON that the
  // sheet has been shared with; it is never committed.
  SHEETS_SERVICE_ACCOUNT: z.string().default('./.secrets/sheets-service-account.json'),
  SHEETS_SHEET_ID: z.string().default('1oKKPnfTCn7LXqO9kboS3Jx2Aw8aWYeVh9PordjNxFeM'),
  SHEETS_TAB: z.string().default('Sheet1'),

  // Operator login for remote access. Unset means the API is open, which is
  // only safe while it stays on 127.0.0.1.
  AUTH_PASSWORD: z.string().optional(),
  AUTH_SECRET: z.string().optional(),
});

export type Env = z.infer<typeof EnvSchema>;

export interface AppConfig {
  env: Env['NODE_ENV'];
  isProduction: boolean;
  host: string;
  port: number;
  logLevel: Env['LOG_LEVEL'];
  corsOrigins: string[];
  paths: {
    databaseFile: string;
    profileDir: string;
    uploadDir: string;
    exportDir: string;
    importDir: string;
    logDir: string;
    webDist: string;
  };
  browser: {
    executablePath: string | null;
    channel: Env['BROWSER_CHANNEL'];
    headless: boolean;
  };
  queue: {
    globalConcurrency: number;
    defaultTimeoutMs: number;
    defaultMaxRetries: number;
    staleJobTimeoutMs: number;
    profileLockTtlMs: number;
  };
  sheets: {
    keyFile: string;
    sheetId: string;
    tab: string;
  };
  auth: {
    /** `null` means no login: every route is open. */
    password: string | null;
    /** Signs tokens. A generated one changes on every start. */
    secret: string;
    secretSource: 'env' | 'generated';
  };
}

/**
 * The only place process.env is read. Everything else takes an AppConfig.
 * A bad value fails the process at startup rather than at first use.
 */
export const loadConfig = (source: NodeJS.ProcessEnv = process.env): AppConfig => {
  const parsed = EnvSchema.safeParse(source);
  if (!parsed.success) {
    const problems = parsed.error.issues
      .map((issue) => `  ${issue.path.join('.')}: ${issue.message}`)
      .join('\n');
    throw new Error(`Invalid environment configuration:\n${problems}`);
  }

  const env = parsed.data;
  const executablePath = env.BROWSER_EXECUTABLE_PATH?.trim();
  const password = env.AUTH_PASSWORD?.trim();
  const secret = env.AUTH_SECRET?.trim();

  return {
    env: env.NODE_ENV,
    isProduction: env.NODE_ENV === 'production',
    host: env.HOST,
    port: env.PORT,
    logLevel: env.LOG_LEVEL,
    corsOrigins: env.CORS_ORIGIN.split(',')
      .map((origin) => origin.trim())
      .filter((origin) => origin.length > 0),
    paths: {
      databaseFile: resolveFromRoot(env.DATABASE_FILE),
      profileDir: resolveFromRoot(env.PROFILE_DIR),
      uploadDir: resolveFromRoot(env.UPLOAD_DIR),
      exportDir: resolveFromRoot(env.EXPORT_DIR),
      importDir: resolveFromRoot(env.IMPORT_DIR),
      logDir: resolveFromRoot(env.LOG_DIR),
      webDist: resolveFromRoot(env.WEB_DIST),
    },
    browser: {
      executablePath: executablePath === undefined || executablePath === '' ? null : executablePath,
      channel: env.BROWSER_CHANNEL,
      headless: env.BROWSER_HEADLESS,
    },
    queue: {
      globalConcurrency: env.GLOBAL_CONCURRENCY,
      defaultTimeoutMs: env.DEFAULT_TIMEOUT_MS,
      defaultMaxRetries: env.DEFAULT_MAX_RETRIES,
      staleJobTimeoutMs: env.STALE_JOB_TIMEOUT_MS,
      profileLockTtlMs: env.PROFILE_LOCK_TTL_MS,
    },
    sheets: {
      keyFile: resolveFromRoot(env.SHEETS_SERVICE_ACCOUNT),
      sheetId: env.SHEETS_SHEET_ID,
      tab: env.SHEETS_TAB,
    },
    auth: {
      password: password === undefined || password === '' ? null : password,
      secret: secret === undefined || secret === '' ? randomBytes(32).toString('hex') : secret,
      secretSource: secret === undefined || secret === '' ? 'generated' : 'env',
    },
  };
};
