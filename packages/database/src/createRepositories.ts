import type { Repositories } from '@fb/application';
import type { DatabaseHandle } from './db.js';
import { AccountRepositoryImpl } from './repositories/AccountRepositoryImpl.js';
import { BrowserProfileRepositoryImpl } from './repositories/BrowserProfileRepositoryImpl.js';
import { ActivityRepositoryImpl, GroupRepositoryImpl } from './repositories/GroupRepositoryImpl.js';
import { JobRepositoryImpl } from './repositories/JobRepositoryImpl.js';
import { LogRepositoryImpl } from './repositories/LogRepositoryImpl.js';
import { SettingsRepositoryImpl } from './repositories/SettingsRepositoryImpl.js';

/**
 * Assembles the persistence surface the application layer expects. The server's
 * container calls this once; nothing else constructs a repository.
 */
export const createRepositories = (handle: DatabaseHandle, workerId: string): Repositories => ({
  accounts: new AccountRepositoryImpl(handle.db),
  profiles: new BrowserProfileRepositoryImpl(handle.db),
  jobs: new JobRepositoryImpl(handle.db, handle.connection, workerId),
  logs: new LogRepositoryImpl(handle.db),
  settings: new SettingsRepositoryImpl(handle.db),
  groups: new GroupRepositoryImpl(handle.db, handle.connection),
  activities: new ActivityRepositoryImpl(handle.db),
});
