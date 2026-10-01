import { z } from 'zod';
import { BROWSER_CHANNELS, DEFAULTS } from '../constants/index.js';

export const BrowserChannelSchema = z.enum(BROWSER_CHANNELS);
export type BrowserChannel = z.infer<typeof BrowserChannelSchema>;

const delayMs = (max: number) => z.number().int().min(0).max(max);

/**
 * Runtime-editable settings. Directory settings are deliberately absent:
 * they come from the environment so the frontend can never repoint storage.
 *
 * The delay ranges exist to protect the accounts. Every share, join and
 * comment waits a random time inside its range, so no two runs share a
 * rhythm. Setting them to zero is possible and unwise.
 */
export const SettingsSchema = z.object({
  browserExecutablePath: z.string().max(1024).nullable(),
  browserChannel: BrowserChannelSchema,
  headless: z.boolean(),
  globalConcurrency: z.number().int().min(1).max(64),
  /**
   * Watch-live jobs run in a lane of their own, outside the global limit: a
   * live is only watched when many accounts watch it at the same time. Zero
   * means every one queued plays at once.
   */
  liveViewersAtOnce: z.number().int().min(0).max(1000),
  defaultTimeoutMs: z.number().int().min(1_000).max(600_000),
  defaultMaxRetries: z.number().int().min(0).max(10),
  retryBackoffMs: z.number().int().min(1_000).max(3_600_000),
  staleJobTimeoutMs: z.number().int().min(60_000).max(86_400_000),
  profileLockTtlMs: z.number().int().min(30_000).max(86_400_000),
  /** Minimum and maximum idle time inserted between automation steps. */
  minActionDelayMs: delayMs(600_000),
  maxActionDelayMs: delayMs(600_000),

  /** Between one group share and the next, per account. */
  betweenSharesMinMs: delayMs(3_600_000),
  betweenSharesMaxMs: delayMs(3_600_000),
  /** After the Share button opens the sheet, before an option is picked. */
  afterShareButtonMinMs: delayMs(600_000),
  afterShareButtonMaxMs: delayMs(600_000),
  /** After Post is pressed, for the share to land before anything else moves. */
  afterPostMinMs: delayMs(600_000),
  afterPostMaxMs: delayMs(600_000),
  betweenJoinsMinMs: delayMs(3_600_000),
  betweenJoinsMaxMs: delayMs(3_600_000),
  afterCommentMinMs: delayMs(600_000),
  afterCommentMaxMs: delayMs(600_000),

  /** How long a paused job waits for a person before it fails. */
  operatorInputTimeoutMs: z.number().int().min(10_000).max(3_600_000),
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
  liveViewersAtOnce: 0,
  defaultTimeoutMs: DEFAULTS.timeoutMs,
  defaultMaxRetries: DEFAULTS.maxRetries,
  retryBackoffMs: DEFAULTS.retryBackoffMs,
  staleJobTimeoutMs: DEFAULTS.staleJobTimeoutMs,
  profileLockTtlMs: DEFAULTS.profileLockTtlMs,
  minActionDelayMs: 800,
  maxActionDelayMs: 2_500,
  betweenSharesMinMs: 15_000,
  betweenSharesMaxMs: 45_000,
  afterShareButtonMinMs: 2_000,
  afterShareButtonMaxMs: 5_000,
  afterPostMinMs: 8_000,
  afterPostMaxMs: 15_000,
  betweenJoinsMinMs: 3_000,
  betweenJoinsMaxMs: 5_000,
  afterCommentMinMs: 3_000,
  afterCommentMaxMs: 5_000,
  operatorInputTimeoutMs: DEFAULTS.operatorInputTimeoutMs,
};

/** Every min/max pair, so the cross-field check and the UI stay in step. */
export const DELAY_RANGES: ReadonlyArray<{
  min: keyof Settings;
  max: keyof Settings;
  label: string;
}> = [
  { min: 'minActionDelayMs', max: 'maxActionDelayMs', label: 'Between steps' },
  { min: 'betweenSharesMinMs', max: 'betweenSharesMaxMs', label: 'Between group shares' },
  { min: 'afterShareButtonMinMs', max: 'afterShareButtonMaxMs', label: 'After the Share button' },
  { min: 'afterPostMinMs', max: 'afterPostMaxMs', label: 'After posting' },
  { min: 'betweenJoinsMinMs', max: 'betweenJoinsMaxMs', label: 'Between group joins' },
  { min: 'afterCommentMinMs', max: 'afterCommentMaxMs', label: 'After a comment' },
];

/** Cross-field rules that a single-field PATCH cannot express. */
export const validateSettings = (settings: Settings): string[] => {
  const problems: string[] = [];
  for (const range of DELAY_RANGES) {
    if ((settings[range.min] as number) > (settings[range.max] as number)) {
      problems.push(`${range.min} must not exceed ${range.max}`);
    }
  }
  if (settings.browserExecutablePath !== null && settings.browserExecutablePath.trim() === '') {
    problems.push('browserExecutablePath must be null rather than an empty string');
  }
  return problems;
};
