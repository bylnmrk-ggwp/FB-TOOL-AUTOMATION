import { z } from 'zod';
import { BROWSER_CHANNELS, DEFAULTS } from '../constants/index.js';

export const BrowserChannelSchema = z.enum(BROWSER_CHANNELS);
export type BrowserChannel = z.infer<typeof BrowserChannelSchema>;

/**
 * Runtime-editable settings. Directory settings are deliberately absent:
 * they come from the environment so the frontend can never repoint storage.
 */
export const SettingsSchema = z.object({
  browserExecutablePath: z.string().max(1024).nullable(),
  browserChannel: BrowserChannelSchema,
  headless: z.boolean(),
  globalConcurrency: z.number().int().min(1).max(32),
  defaultTimeoutMs: z.number().int().min(1_000).max(600_000),
  defaultMaxRetries: z.number().int().min(0).max(10),
  retryBackoffMs: z.number().int().min(1_000).max(3_600_000),
  staleJobTimeoutMs: z.number().int().min(60_000).max(86_400_000),
  profileLockTtlMs: z.number().int().min(30_000).max(86_400_000),
  /** Minimum and maximum idle time inserted between automation steps. */
  minActionDelayMs: z.number().int().min(0).max(600_000),
  maxActionDelayMs: z.number().int().min(0).max(600_000),
});
export type Settings = z.infer<typeof SettingsSchema>;

export const UpdateSettingsSchema = SettingsSchema.partial().refine(
  (value) => Object.keys(value).length > 0,
  'Provide at least one setting to update',
);
export type UpdateSettingsInput = z.infer<typeof UpdateSettingsSchema>;

/** Read-only view of the paths the server was started with. */
export const SystemPathsSchema = z.object({
  profileDir: z.string(),
  uploadDir: z.string(),
  exportDir: z.string(),
  importDir: z.string(),
  logDir: z.string(),
  databaseFile: z.string(),
});
export type SystemPaths = z.infer<typeof SystemPathsSchema>;

export const DEFAULT_SETTINGS: Settings = {
  browserExecutablePath: null,
  browserChannel: 'chromium',
  headless: false,
  globalConcurrency: DEFAULTS.globalConcurrency,
  defaultTimeoutMs: DEFAULTS.timeoutMs,
  defaultMaxRetries: DEFAULTS.maxRetries,
  retryBackoffMs: DEFAULTS.retryBackoffMs,
  staleJobTimeoutMs: DEFAULTS.staleJobTimeoutMs,
  profileLockTtlMs: DEFAULTS.profileLockTtlMs,
  minActionDelayMs: 800,
  maxActionDelayMs: 2_500,
};

/** Cross-field rules that a single-field PATCH cannot express. */
export const validateSettings = (settings: Settings): string[] => {
  const problems: string[] = [];
  if (settings.minActionDelayMs > settings.maxActionDelayMs) {
    problems.push('minActionDelayMs must not exceed maxActionDelayMs');
  }
  if (settings.browserExecutablePath !== null && settings.browserExecutablePath.trim() === '') {
    problems.push('browserExecutablePath must be null rather than an empty string');
  }
  return problems;
};
