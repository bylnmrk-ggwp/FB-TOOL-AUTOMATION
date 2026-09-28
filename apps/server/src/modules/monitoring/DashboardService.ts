import type { DashboardStats } from '@fb/shared';
import type { QueuePort, Repositories } from '@fb/application';

/**
 * The one read that the Dashboard needs, assembled server-side.
 *
 * Doing it here rather than in five separate requests keeps the numbers
 * consistent with each other: they all describe the same moment.
 */
export class DashboardService {
  constructor(
    private readonly repositories: Repositories,
    private readonly queue: QueuePort,
  ) {}

  async stats(): Promise<DashboardStats> {
    const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);

    const [accountCounts, queueStats, recent, since] = await Promise.all([
      this.repositories.accounts.countByStatus(),
      this.repositories.jobs.stats(),
      this.repositories.logs.recent(20),
      this.repositories.jobs.statsSince(dayAgo),
    ]);

    const accountsTotal = Object.values(accountCounts).reduce((sum, value) => sum + value, 0);
    const enabled = await this.repositories.accounts.list({ limit: 1, offset: 0, enabled: true });
    const capacity = this.queue.capacity();

    return {
      accounts: {
        total: accountsTotal,
        enabled: enabled.total,
        online: accountCounts.online,
        busy: accountCounts.busy,
        error: accountCounts.error,
      },
      queue: queueStats,
      jobs: {
        last24h: since.total,
        succeededLast24h: since.succeeded,
        failedLast24h: since.failed,
      },
      health: {
        // Degraded when work is waiting and nothing can pick it up.
        status: capacity.limit > 0 ? 'ok' : 'degraded',
        workersBusy: capacity.busy,
        workerCapacity: capacity.limit,
      },
      recentActivity: recent,
    };
  }
}
