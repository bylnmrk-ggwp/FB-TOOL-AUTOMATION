import type { Settings } from '@fb/shared';

export interface SettingsRepository {
  read(): Promise<Settings>;
  write(patch: Partial<Settings>): Promise<Settings>;
}
