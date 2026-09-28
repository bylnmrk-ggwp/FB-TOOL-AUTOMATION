import { join } from 'node:path';
import {
  AccountService,
  BrowserService,
  GroupService,
  JobService,
  OperatorInputService,
  RosterService,
  SessionService,
  type EventBus,
  type FileStore,
  type Logger,
  type Repositories,
} from '@fb/application';
import {
  BrowserManager,
  FacebookAutomation,
  FileProfileLockManager,
  ProfileManager,
  SessionTransfer,
} from '@fb/automation';
import {
  createDatabase,
  createRepositories,
  runMigrations,
  type DatabaseHandle,
} from '@fb/database';
import type { AutomationGateway, BrowserController } from '@fb/domain';
import { createLogger, InMemoryEventBus, PersistentLogger } from '@fb/observability';
import { QueueManager } from '@fb/queue';
import type { AppConfig } from '../config/index.js';
import { HealthService } from '../modules/health/HealthService.js';
import { UploadFileStore } from '../modules/media/UploadFileStore.js';
import { DashboardService } from '../modules/monitoring/DashboardService.js';
import { GoogleSheetsSource } from '../modules/roster/GoogleSheetsSource.js';

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
  files: FileStore;
  accounts: AccountService;
  browsers: BrowserService;
  browserManager: BrowserManager;
  sessions: SessionService;
  groups: GroupService;
  operator: OperatorInputService;
  roster: RosterService;
  rosterSheet: GoogleSheetsSource;
  jobs: JobService;
  queue: QueueManager;
  dashboard: DashboardService;
  health: HealthService;
  /** Identifies this process in profile and job locks. */
  workerId: string;
  start: () => Promise<void>;
  shutdown: () => Promise<void>;
}

export interface ContainerOverrides {
  /** Replaces the Playwright-backed controller, so tests can run without a browser. */
  browserController?: BrowserController;
  /** Replaces the Facebook gateway, so tests can exercise the queue without a site. */
  gateway?: AutomationGateway;
  /** Leaves the queue stopped, for tests that drive it by hand. */
  autoStartQueue?: boolean;
}

export const createContainer = (
  config: AppConfig,
  overrides: ContainerOverrides = {},
): Container => {
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
  const files = new UploadFileStore(config.paths.uploadDir);

  const browserManager = new BrowserManager(logger);
  const browserController = overrides.browserController ?? browserManager;
  const browsers = new BrowserService({
    repositories,
    controller: browserController,
    locks,
    profiles,
    events,
    logger,
    workerId,
  });

  const sessions = new SessionService({
    repositories,
    controller: browserController,
    profiles,
    transfer: new SessionTransfer(),
    logger,
  });

  const groups = new GroupService(repositories, events, logger);
  const operator = new OperatorInputService(events, logger);

  const gateway =
    overrides.gateway ??
    new FacebookAutomation({
      contexts: browserManager,
      files,
      logger,
      credentials: { credentials: (accountId) => repositories.accounts.credentials(accountId) },
    });

  // The account service is built before the queue and rebuilt after: the
  // queue needs it for login verdicts, and deletion needs the queue to stop
  // a running job. One instance, two references.
  const accounts = new AccountService({ repositories, profiles, events, logger });

  const queue = new QueueManager({
    repositories,
    gateway,
    browsers,
    accounts,
    groups,
    operator,
    events,
    logger,
  });
  const jobs = new JobService({ repositories, queue, events, logger });
  accounts.attach({ sessions: browsers, queue });

  const roster = new RosterService(accounts, logger);
  const rosterSheet = new GoogleSheetsSource(config.sheets);
  const dashboard = new DashboardService(repositories, queue);

  const health = new HealthService({
    database: () => database.connection.isHealthy(),
    queue: () => queue.isRunning(),
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

    // The environment seeds the settings once; after that the Settings page
    // owns them and a changed .env no longer overwrites an operator's choice.
    if (!(await repositories.settings.isInitialised())) {
      await repositories.settings.write({
        browserExecutablePath: config.browser.executablePath,
        browserChannel: config.browser.channel,
        headless: config.browser.headless,
        globalConcurrency: config.queue.globalConcurrency,
        defaultTimeoutMs: config.queue.defaultTimeoutMs,
        defaultMaxRetries: config.queue.defaultMaxRetries,
        staleJobTimeoutMs: config.queue.staleJobTimeoutMs,
        profileLockTtlMs: config.queue.profileLockTtlMs,
      });
      logger.info('Seeded the settings from the environment', { event: 'settings.seeded' });
    }

    browsers.listen();
    if (overrides.autoStartQueue !== false) await queue.start();
  };

  const shutdown = async (): Promise<void> => {
    // Order matters: stop taking work, let what is running finish, then close
    // the browsers it was using, and only then the database it writes to.
    operator.cancelAll();
    await queue.stop();
    browsers.stopListening();
    await browsers.stopAll();
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
    files,
    accounts,
    browsers,
    browserManager,
    sessions,
    groups,
    operator,
    roster,
    rosterSheet,
    jobs,
    queue,
    dashboard,
    health,
    workerId,
    start,
    shutdown,
  };
};
