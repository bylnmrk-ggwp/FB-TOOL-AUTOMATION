import type { EventBus, Logger } from '@fb/application';
import { createLogger, InMemoryEventBus } from '@fb/observability';
import { join } from 'node:path';
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
  health: HealthService;
  shutdown: () => Promise<void>;
}

export const createContainer = (config: AppConfig): Container => {
  const logger = createLogger({
    level: config.logLevel,
    pretty: !config.isProduction,
    filePath: join(config.paths.logDir, 'server.log'),
  });

  const events = new InMemoryEventBus();

  // Phase 1 has no database or queue yet, so both probes report down until the
  // later phases replace them in this same place.
  const health = new HealthService({
    database: () => false,
    queue: () => false,
  });

  const shutdown = async (): Promise<void> => {
    logger.info('Shutdown complete', { event: 'server.shutdown' });
  };

  return { config, logger, events, health, shutdown };
};
