import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { isAbsolute, join, resolve } from 'node:path';

/**
 * Copies the SQLite file, plus its write-ahead log, into data/exports with a
 * timestamped name. The WAL matters: copying the .sqlite alone can leave out
 * the most recent commits.
 */
const main = (): void => {
  const root = resolve(import.meta.dirname, '..');
  try {
    process.loadEnvFile(join(root, '.env'));
  } catch {
    // Defaults below apply.
  }

  const configured = process.env['DATABASE_FILE'] ?? './data/database/fb-automation.sqlite';
  const source = isAbsolute(configured) ? configured : resolve(root, configured);

  if (!existsSync(source)) {
    console.error(`No database at ${source}`);
    process.exit(1);
  }

  const exportDir = resolve(root, process.env['EXPORT_DIR'] ?? './data/exports');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const target = join(exportDir, `backup-${stamp}.sqlite`);

  mkdirSync(exportDir, { recursive: true });
  copyFileSync(source, target);

  for (const suffix of ['-wal', '-shm']) {
    if (existsSync(`${source}${suffix}`)) copyFileSync(`${source}${suffix}`, `${target}${suffix}`);
  }

  console.log(`Backup written to ${target}`);
};

main();
