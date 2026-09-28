import { join } from 'node:path';
import { AccountService, type EventBus, type Logger, type Repositories } from '@fb/application';
import { FileProfileLockManager, ProfileManager } from '@fb/automation';
import {
  createDatabase,
  createRepositories,
  runMigrations,
  type DatabaseHandle,
} from '@fb/database';
import { createLogger, InMemoryEventBus, PersistentLogger } from '@fb/observability';
import type { AppConfig } from '../config/index.js';
import { HealthService } from '../modules/health/HealthService.js';

/**
 * Composition root. Every concrete implementation is chosen here and nowhere
 * else, which is what keeps the layers below free of wiring decisions.
 */
export interface Container {
  config: AppConfig;
  logger: Logger;
  events: EventBus;
  database: DatabaseHandle;
  repositories: Repositories;
  profiles: ProfileManager;
  locks: FileProfileLockManager;
  accounts: AccountService;
  health: HealthService;
  /** Identifies this process in profile and job locks. */
  workerId: string;
  start: () => Promise<void>;
  shutdown: () => Promise<void>;
}

export const createContainer = (config: AppConfig): Container => {
  const workerId = `${process.pid}@${config.host}:${config.port}`;

  const consoleLogger = createLogger({
    level: config.logLevel,
    pretty: !config.isProduction,
    filePath: join(config.paths.logDir, 'server.log'),
  });

  const events = new InMemoryEventBus();

  const database = createDatabase(config.paths.databaseFile);
  const repositories = createRepositories(database, workerId);

  // Logging is wired after the repositories exist so every line also lands in
  // the database and on the live feed.
  const logger: Logger = new PersistentLogger(consoleLogger, repositories.logs, events);

  const profiles = new ProfileManager(config.paths.profileDir);
  const locks = new FileProfileLockManager(
    repositories.profiles,
    profiles,
    logger,
    config.queue.profileLockTtlMs,
  );

  const accounts = new AccountService({ repositories, profiles, events, logger });

  const health = new HealthService({
    database: () => database.connection.isHealthy(),
    // Phase 7 replaces this with the queue's own readiness.
    queue: () => true,
  });

  const start = async (): Promise<void> => {
    const migrations = runMigrations(database.connection);
    if (migrations.applied.length > 0) {
      logger.info(`Applied ${migrations.applied.length} migration(s)`, {
        event: 'database.migrated',
        migrations: migrations.applied,
      });
    }

    // Nothing survives a restart: sessions are gone, so the rows that claimed
    // to have one are corrected before the API starts answering.
    const reset = await repositories.accounts.resetRuntimeStatuses();
    if (reset > 0) {
      logger.warn(`Reset ${reset} account(s) left mid-session by the previous run`, {
        event: 'accounts.reset',
      });
    }

    const released = await locks.releaseOwnedBy(workerId);
    const reaped = await locks.reapStale();
    if (released + reaped > 0) {
      logger.info(`Cleared ${released + reaped} profile lock(s) left behind`, {
        event: 'profile.locks.cleared',
      });
    }
  };

  const shutdown = async (): Promise<void> => {
    await locks.releaseOwnedBy(workerId);
    database.close();
    consoleLogger.info('Shutdown complete', { event: 'server.shutdown' });
  };

  return {
    config,
    logger,
    events,
    database,
    repositories,
    profiles,
    locks,
    accounts,
    health,
    workerId,
    start,
    shutdown,
  };
};
