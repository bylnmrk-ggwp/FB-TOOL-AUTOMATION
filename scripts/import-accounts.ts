import { readFileSync } from 'node:fs';
import { isAbsolute, join, resolve } from 'node:path';
import { API_PREFIX, ImportAccountsResultSchema } from '@fb/shared';

/**
 * Imports accounts from a JSON or CSV file through the running API, rather
 * than writing to the database directly: the same validation, the same profile
 * directories, and the same events the UI would have produced.
 *
 *   pnpm tsx scripts/import-accounts.ts ./data/imports/accounts.csv [--upsert]
 *
 * CSV is read as `name,displayName,enabled`, with an optional header row.
 */
interface Row {
  name: string;
  displayName?: string;
  enabled?: boolean;
}

const parseCsv = (contents: string): Row[] => {
  const lines = contents
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const rows: Row[] = [];
  for (const [index, line] of lines.entries()) {
    const [name, displayName, enabled] = line.split(',').map((cell) => cell.trim());
    if (name === undefined || name === '') continue;
    // A first row that names the columns is a header, not an account.
    if (index === 0 && name.toLowerCase() === 'name') continue;

    rows.push({
      name,
      ...(displayName === undefined || displayName === '' ? {} : { displayName }),
      ...(enabled === undefined || enabled === ''
        ? {}
        : { enabled: !['false', '0', 'no'].includes(enabled.toLowerCase()) }),
    });
  }
  return rows;
};

const parseFile = (path: string): Row[] => {
  const contents = readFileSync(path, 'utf8');
  if (path.toLowerCase().endsWith('.csv')) return parseCsv(contents);

  const parsed: unknown = JSON.parse(contents);
  const list = Array.isArray(parsed) ? parsed : ((parsed as { accounts?: unknown }).accounts ?? []);
  if (!Array.isArray(list)) throw new Error('Expected an array, or an object with `accounts`');
  return list as Row[];
};

const main = async (): Promise<void> => {
  const root = resolve(import.meta.dirname, '..');
  try {
    process.loadEnvFile(join(root, '.env'));
  } catch {
    // Defaults below apply.
  }

  const [inputArg, ...flags] = process.argv.slice(2);
  if (inputArg === undefined) {
    console.error('Usage: tsx scripts/import-accounts.ts <file.json|file.csv> [--upsert]');
    process.exit(1);
  }

  const path = isAbsolute(inputArg) ? inputArg : resolve(root, inputArg);
  const accounts = parseFile(path);
  if (accounts.length === 0) {
    console.error(`No accounts found in ${path}`);
    process.exit(1);
  }

  const host = process.env['HOST'] ?? '127.0.0.1';
  const port = process.env['PORT'] ?? '3001';
  const url = `http://${host}:${port}${API_PREFIX}/accounts/import`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ accounts, upsert: flags.includes('--upsert') }),
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    console.error(`Import failed with ${response.status}:`, JSON.stringify(payload));
    process.exit(1);
  }

  const result = ImportAccountsResultSchema.parse(payload);
  console.log(`Created ${result.created}, updated ${result.updated}`);
  for (const skipped of result.skipped) console.log(`  skipped ${skipped.name}: ${skipped.reason}`);
};

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
