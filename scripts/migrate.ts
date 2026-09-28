import { join, isAbsolute, resolve } from 'node:path';
import { createDatabase, runMigrations } from '@fb/database';

/**
 * Applies pending migrations from the command line. The server does the same
 * thing at startup; this exists for deployments that migrate as a separate step.
 */
const main = (): void => {
  const root = resolve(import.meta.dirname, '..');
  try {
    process.loadEnvFile(join(root, '.env'));
  } catch {
    // No .env file: fall back to the default location below.
  }

  const configured = process.env['DATABASE_FILE'] ?? './data/database/fb-automation.sqlite';
  const file = isAbsolute(configured) ? configured : resolve(root, configured);

  const handle = createDatabase(file);
  try {
    const result = runMigrations(handle.connection);
    if (result.applied.length === 0) {
      console.log(`No pending migrations (${result.alreadyApplied} already applied): ${file}`);
    } else {
      console.log(`Applied ${result.applied.length} migration(s) to ${file}`);
      for (const name of result.applied) console.log(`  ${name}`);
    }
  } finally {
    handle.close();
  }
};

main();
