import type { Settings } from '@fb/shared';

export interface SettingsRepository {
  read(): Promise<Settings>;
  write(patch: Partial<Settings>): Promise<Settings>;
  /** False until something has been stored, which is how first-run seeding knows. */
  isInitialised(): Promise<boolean>;
}
