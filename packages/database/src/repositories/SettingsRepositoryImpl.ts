import { eq } from 'drizzle-orm';
import type { Settings } from '@fb/shared';
import { DEFAULT_SETTINGS, nowIso, SettingsSchema } from '@fb/shared';
import type { SettingsRepository } from '@fb/domain';
import type { Database } from '../db.js';
import { settings } from '../schema/settings.js';

const ROW_KEY = 'system';

/**
 * Stored values are merged over DEFAULT_SETTINGS, so a setting added in a later
 * version has a sensible value on an existing database without a migration.
 */
export class SettingsRepositoryImpl implements SettingsRepository {
  constructor(private readonly db: Database) {}

  async read(): Promise<Settings> {
    const rows = await this.db.select().from(settings).where(eq(settings.key, ROW_KEY)).limit(1);
    const row = rows[0];
    if (row === undefined) return DEFAULT_SETTINGS;

    const stored: unknown = JSON.parse(row.value);
    const merged = { ...DEFAULT_SETTINGS, ...(stored as Record<string, unknown>) };

    const parsed = SettingsSchema.safeParse(merged);
    // A stored value that no longer validates must not stop the server from
    // starting; the defaults win and the bad value is overwritten on next save.
    return parsed.success ? parsed.data : DEFAULT_SETTINGS;
  }

  async isInitialised(): Promise<boolean> {
    const rows = await this.db
      .select({ key: settings.key })
      .from(settings)
      .where(eq(settings.key, ROW_KEY))
      .limit(1);
    return rows[0] !== undefined;
  }

  async write(patch: Partial<Settings>): Promise<Settings> {
    const current = await this.read();
    const next = SettingsSchema.parse({ ...current, ...patch });
    const updatedAt = nowIso();

    if (!(await this.isInitialised())) {
      await this.db
        .insert(settings)
        .values({ key: ROW_KEY, value: JSON.stringify(next), updatedAt });
    } else {
      await this.db
        .update(settings)
        .set({ value: JSON.stringify(next), updatedAt })
        .where(eq(settings.key, ROW_KEY));
    }

    return next;
  }
}
