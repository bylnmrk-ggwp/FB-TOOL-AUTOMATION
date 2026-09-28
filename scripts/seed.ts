import { mkdirSync } from 'node:fs';
import { isAbsolute, join, resolve } from 'node:path';
import { createDatabase, createRepositories, runMigrations } from '@fb/database';
import { createId, slugify } from '@fb/shared';

/**
 * Creates a handful of accounts for a fresh checkout, so the UI has something
 * to show before anybody signs in to Facebook. Existing accounts are left
 * alone, so running this twice is harmless.
 */
const SEED_ACCOUNTS = ['Demo One', 'Demo Two', 'Demo Three'];

const main = async (): Promise<void> => {
  const root = resolve(import.meta.dirname, '..');
  try {
    process.loadEnvFile(join(root, '.env'));
  } catch {
    // Defaults below apply.
  }

  const configured = process.env['DATABASE_FILE'] ?? './data/database/fb-automation.sqlite';
  const file = isAbsolute(configured) ? configured : resolve(root, configured);

  const handle = createDatabase(file);
  runMigrations(handle.connection);
  const repositories = createRepositories(handle, 'seed-script');

  try {
    for (const name of SEED_ACCOUNTS) {
      if ((await repositories.accounts.findByName(name)) !== null) {
        console.log(`Skipped ${name}: it already exists`);
        continue;
      }

      const accountId = createId('acc');
      const profileId = createId('prf');
      const slug = slugify(name);

      await repositories.accounts.create({
        id: accountId,
        name,
        displayName: name,
        profileId,
        status: 'offline',
        enabled: true,
      });
      await repositories.profiles.create({
        id: profileId,
        accountId,
        slug,
        directory: slug,
        channel: 'chromium',
      });

      // The directory is created here too, so a seeded account looks exactly
      // like one made through the UI.
      const profileRoot = resolve(root, process.env['PROFILE_DIR'] ?? './data/browser-profiles');
      mkdirSync(join(profileRoot, slug), { recursive: true });

      console.log(`Created ${name} with profile ${slug}`);
    }
  } finally {
    handle.close();
  }
};

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
