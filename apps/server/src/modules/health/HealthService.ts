import type { Health } from '@fb/shared';
import { SERVER_VERSION } from '../../config/version.js';

export type Probe = () => boolean | Promise<boolean>;

export interface HealthProbes {
  database: Probe;
  queue: Probe;
}

/**
 * Reports what the process can actually verify right now. A probe that throws
 * counts as down rather than failing the request.
 */
export class HealthService {
  private readonly startedAt = Date.now();

  constructor(private readonly probes: HealthProbes) {}

  async check(): Promise<Health> {
    const [database, queue] = await Promise.all([
      this.run(this.probes.database),
      this.run(this.probes.queue),
    ]);

    const healthy = database === 'up' && queue === 'up';
    return {
      status: healthy ? 'ok' : 'degraded',
      version: SERVER_VERSION,
      uptimeSeconds: Math.round((Date.now() - this.startedAt) / 1000),
      timestamp: new Date().toISOString(),
      checks: { database, queue },
    };
  }

  private async run(probe: Probe): Promise<'up' | 'down'> {
    try {
      return (await probe()) ? 'up' : 'down';
    } catch {
      return 'down';
    }
  }
}
