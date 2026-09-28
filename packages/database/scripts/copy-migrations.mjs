import { cpSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// tsc only emits JavaScript, so the generated .sql files have to be placed
// next to the compiled migrator for `runMigrations()` to find them.
const packageRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const from = join(packageRoot, 'src', 'migrations');
const to = join(packageRoot, 'dist', 'migrations');

if (!existsSync(from)) {
  console.error(`No migrations directory at ${from}`);
  process.exit(1);
}

cpSync(from, to, { recursive: true });
