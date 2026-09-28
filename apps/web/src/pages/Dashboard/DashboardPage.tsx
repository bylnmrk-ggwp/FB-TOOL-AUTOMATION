import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';
import type { DashboardStats } from '@fb/shared';
import { Card } from '../../components/ui/Card';
import { LogLevelBadge } from '../../components/ui/Badge';
import { ErrorNotice, Loading } from '../../components/ui/Feedback';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusDot, type StatusTone } from '../../components/ui/StatusDot';
import { useDashboard } from '../../features/monitoring/hooks';
import { useHealth } from '../../hooks/useHealth';
import { relativeTime } from '../../lib/format';
import './DashboardPage.css';

interface Metric {
  label: string;
  value: number;
  tone?: StatusTone;
  to?: string;
}

const metricsFor = (stats: DashboardStats): Metric[] => [
  { label: 'Accounts', value: stats.accounts.total, to: '/accounts' },
  { label: 'Online', value: stats.accounts.online, tone: 'ok', to: '/accounts' },
  { label: 'Busy', value: stats.accounts.busy, tone: 'info', to: '/monitor' },
  { label: 'In error', value: stats.accounts.error, tone: 'danger', to: '/accounts' },
  {
    label: 'Queued',
    value: stats.queue.pending + stats.queue.queued + stats.queue.retrying,
    to: '/queue',
  },
  { label: 'Running', value: stats.queue.running, tone: 'info', to: '/monitor' },
  { label: 'Failed', value: stats.queue.failed, tone: 'danger', to: '/queue' },
  { label: 'Completed', value: stats.queue.completed, tone: 'ok', to: '/queue' },
];

export const DashboardPage = (): ReactElement => {
  const dashboard = useDashboard();
  const health = useHealth();

  return (
    <div className="page">
      <PageHeader title="Dashboard" description="What the automation system is doing right now." />

      {dashboard.isError && <ErrorNotice error={dashboard.error} />}
      {dashboard.isPending && <Loading label="Collecting statistics…" />}

      {dashboard.isSuccess && (
        <>
          <section className="metrics">
            {metricsFor(dashboard.data).map((metric) => (
              <MetricTile key={metric.label} metric={metric} />
            ))}
          </section>

          <div className="dashboard__columns">
            <Card title="Last 24 hours">
              <dl className="dashboard__facts">
                <Fact label="Jobs created" value={String(dashboard.data.jobs.last24h)} />
                <Fact label="Succeeded" value={String(dashboard.data.jobs.succeededLast24h)} />
                <Fact label="Failed" value={String(dashboard.data.jobs.failedLast24h)} />
                <Fact
                  label="Workers"
                  value={`${dashboard.data.health.workersBusy} of ${dashboard.data.health.workerCapacity} busy`}
                />
              </dl>
            </Card>

            <Card title="System">
              <div className="dashboard__checks">
                <StatusDot
                  tone={health.data?.checks.database === 'up' ? 'ok' : 'danger'}
                  label={`Database ${health.data?.checks.database ?? 'unknown'}`}
                />
                <StatusDot
                  tone={health.data?.checks.queue === 'up' ? 'ok' : 'danger'}
                  label={`Queue ${health.data?.checks.queue ?? 'unknown'}`}
                />
                <StatusDot
                  tone={dashboard.data.health.status === 'ok' ? 'ok' : 'warn'}
                  label={`Automation ${dashboard.data.health.status}`}
                />
              </div>
            </Card>
          </div>

          <Card title="Recent activity">
            {dashboard.data.recentActivity.length === 0 ? (
              <p className="muted">Nothing has happened yet.</p>
            ) : (
              <ul className="activity">
                {dashboard.data.recentActivity.map((entry) => (
                  <li key={entry.id} className="activity__row">
                    <LogLevelBadge level={entry.level} />
                    <span className="activity__message">{entry.message}</span>
                    <span className="activity__time">{relativeTime(entry.createdAt)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
};

const MetricTile = ({ metric }: { metric: Metric }): ReactElement => {
  const body = (
    <>
      <span className="metric__value">{metric.value}</span>
      <span className="metric__label">{metric.label}</span>
    </>
  );

  return metric.to === undefined ? (
    <div className={`metric metric--${metric.tone ?? 'neutral'}`}>{body}</div>
  ) : (
    <Link to={metric.to} className={`metric metric--${metric.tone ?? 'neutral'}`}>
      {body}
    </Link>
  );
};

const Fact = ({ label, value }: { label: string; value: string }): ReactElement => (
  <div>
    <dt>{label}</dt>
    <dd>{value}</dd>
  </div>
);
