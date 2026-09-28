import { LOGIN_STATUSES, type DashboardStats, type HourlyJobs, type LoginStatus } from '@fb/shared';
import type { QueuePort, Repositories } from '@fb/application';

const HOURS = 24;

/**
 * The one read that the Dashboard needs, assembled server-side.
 *
 * Doing it here rather than in several requests keeps the numbers consistent
 * with each other: they all describe the same moment.
 */
export class DashboardService {
  constructor(
    private readonly repositories: Repositories,
    private readonly queue: QueuePort,
  ) {}

  async stats(): Promise<DashboardStats> {
    const now = new Date();
    const dayAgo = new Date(now.getTime() - HOURS * 60 * 60 * 1000);

    const [accountCounts, loginCounts, queueStats, recent, since, byHour, byType, enabled] =
      await Promise.all([
        this.repositories.accounts.countByStatus(),
        this.repositories.accounts.countByLoginStatus(),
        this.repositories.jobs.stats(),
        this.repositories.logs.recent(20),
        this.repositories.jobs.statsSince(dayAgo),
        this.repositories.jobs.finishedByHour(dayAgo),
        this.repositories.jobs.finishedByType(dayAgo),
        this.repositories.accounts.list({ limit: 1, offset: 0, enabled: true }),
      ]);

    const accountsTotal = Object.values(accountCounts).reduce((sum, value) => sum + value, 0);
    const capacity = this.queue.capacity();

    return {
      accounts: {
        total: accountsTotal,
        enabled: enabled.total,
        online: accountCounts.online,
        busy: accountCounts.busy,
        error: accountCounts.error,
        byLoginStatus: Object.fromEntries(
          LOGIN_STATUSES.map((status) => [status, loginCounts[status] ?? 0]),
        ) as Record<LoginStatus, number>,
      },
      queue: queueStats,
      jobs: {
        last24h: since.total,
        succeededLast24h: since.succeeded,
        failedLast24h: since.failed,
        hourly: fillHours(byHour, now),
        byType: byType.map((row) => ({ type: row.type, count: row.count })),
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

/**
 * Every one of the last 24 hours, oldest first, zero where nothing finished.
 * A chart with gaps in its x-axis reads as missing data, not as quiet hours.
 */
const fillHours = (
  rows: ReadonlyArray<{ hour: string; status: string; count: number }>,
  now: Date,
): HourlyJobs[] => {
  const buckets = new Map<string, HourlyJobs>();
  const start = new Date(now);
  start.setUTCMinutes(0, 0, 0);

  for (let offset = HOURS - 1; offset >= 0; offset -= 1) {
    const hour = new Date(start.getTime() - offset * 60 * 60 * 1000).toISOString();
    buckets.set(hour, { hour, completed: 0, failed: 0, cancelled: 0 });
  }

  for (const row of rows) {
    const bucket = buckets.get(row.hour);
    if (bucket === undefined) continue;
    if (row.status === 'completed') bucket.completed += row.count;
    else if (row.status === 'failed') bucket.failed += row.count;
    else if (row.status === 'cancelled') bucket.cancelled += row.count;
  }

  return [...buckets.values()];
};
