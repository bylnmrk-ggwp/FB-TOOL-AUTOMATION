import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createDatabase, runMigrations, type DatabaseHandle } from '@fb/database';

export interface TestDatabase extends DatabaseHandle {
  directory: string;
  dispose: () => void;
}

/** A migrated SQLite database in a throwaway directory. */
export const createTestDatabase = (): TestDatabase => {
  const directory = mkdtempSync(join(tmpdir(), 'fb-automation-test-'));
  const handle = createDatabase(join(directory, 'test.sqlite'));
  runMigrations(handle.connection);

  return {
    ...handle,
    directory,
    dispose: () => {
      handle.close();
      rmSync(directory, { recursive: true, force: true });
    },
  };
};
