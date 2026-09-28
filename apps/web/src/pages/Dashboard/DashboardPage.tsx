import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import type { DashboardStats } from '@fb/shared';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { LogLevelDot, StatusDot } from '@/components/common/StatusDot';
import { EmptyState, ErrorNotice, Loading } from '@/components/common/Feedback';
import { PageHeader } from '@/components/common/PageHeader';
import { cn } from '@/lib/utils';
import {
  HourlyJobsChart,
  JobsByTypeChart,
  RosterHealthBar,
} from '../../features/monitoring/components/charts';
import { useDashboard } from '../../features/monitoring/hooks';
import { useHealth } from '../../hooks/useHealth';
import { relativeTime } from '../../lib/format';

interface Figure {
  label: string;
  value: number;
  to: string;
  /** Only failure counts get colour, and only when they are not zero. */
  alarm?: boolean;
}

const figuresFor = (stats: DashboardStats): { accounts: Figure[]; queue: Figure[] } => ({
  accounts: [
    { label: 'Total', value: stats.accounts.total, to: '/accounts' },
    {
      label: 'Logged in',
      value: stats.accounts.byLoginStatus.logged_in ?? 0,
      to: '/accounts?login=logged_in',
    },
    { label: 'Browser open', value: stats.accounts.online + stats.accounts.busy, to: '/monitor' },
    { label: 'Need attention', value: needAttention(stats), to: '/accounts', alarm: true },
  ],
  queue: [
    {
      label: 'Waiting',
      value: stats.queue.pending + stats.queue.queued + stats.queue.retrying,
      to: '/queue',
    },
    { label: 'Running', value: stats.queue.running, to: '/monitor' },
    { label: 'Completed', value: stats.queue.completed, to: '/queue?filter=completed' },
    { label: 'Failed', value: stats.queue.failed, to: '/queue?filter=failed', alarm: true },
  ],
});

const needAttention = (stats: DashboardStats): number => {
  const by = stats.accounts.byLoginStatus;
  return (
    (by.checkpoint ?? 0) +
    (by.two_factor ?? 0) +
    (by.email_confirmation ?? 0) +
    (by.captcha ?? 0) +
    (by.disabled ?? 0) +
    (by.logged_out ?? 0)
  );
};

/**
 * One strip of figures, split into the two things an operator asks about —
 * accounts and work — rather than a grid of identical tiles. Failures are the
 * only figures that take colour, and only when there is something to see.
 */
const FigureStrip = ({ title, figures }: { title: string; figures: Figure[] }): ReactElement => (
  <Card className="gap-0 py-0">
    <CardHeader className="border-b px-5 py-3">
      <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
    </CardHeader>
    <CardContent className="grid grid-cols-2 divide-x px-0 sm:grid-cols-4">
      {figures.map((figure) => (
        <Link
          key={figure.label}
          to={figure.to}
          className="group flex flex-col gap-1 px-5 py-4 transition-colors hover:bg-accent/60"
        >
          <span
            className={cn(
              'tabular text-2xl font-semibold tracking-tight',
              figure.alarm && figure.value > 0 && 'text-destructive',
            )}
          >
            {figure.value}
          </span>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            {figure.label}
            <ArrowRight className="size-3 opacity-0 transition-opacity group-hover:opacity-100" />
          </span>
        </Link>
      ))}
    </CardContent>
  </Card>
);

export const DashboardPage = (): ReactElement => {
  const dashboard = useDashboard();
  const health = useHealth();

  return (
    <div className="grid gap-6">
      <PageHeader title="Dashboard" description="What the system is doing right now." />

      {dashboard.isError && <ErrorNotice error={dashboard.error} />}
      {dashboard.isPending && <Loading rows={4} />}

      {dashboard.isSuccess && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <FigureStrip title="Accounts" figures={figuresFor(dashboard.data).accounts} />
            <FigureStrip title="Queue" figures={figuresFor(dashboard.data).queue} />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <Card>
              <CardContent className="grid gap-6">
                <HourlyJobsChart data={dashboard.data.jobs.hourly} />
                <Separator />
                <div className="grid gap-6 md:grid-cols-2">
                  <RosterHealthBar counts={dashboard.data.accounts.byLoginStatus} />
                  <JobsByTypeChart data={dashboard.data.jobs.byType} />
                </div>
              </CardContent>
            </Card>

            <div className="grid content-start gap-4">
              <Card className="gap-0 py-0">
                <CardHeader className="border-b px-5 py-3">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    System
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 px-5 py-4">
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
                  <Separator />
                  <dl className="grid grid-cols-2 gap-y-2 text-sm">
                    <dt className="text-muted-foreground">Workers</dt>
                    <dd className="tabular text-right">
                      {dashboard.data.health.workersBusy} of {dashboard.data.health.workerCapacity}
                    </dd>
                    <dt className="text-muted-foreground">Jobs, 24 h</dt>
                    <dd className="tabular text-right">{dashboard.data.jobs.last24h}</dd>
                    <dt className="text-muted-foreground">Succeeded</dt>
                    <dd className="tabular text-right">{dashboard.data.jobs.succeededLast24h}</dd>
                    <dt className="text-muted-foreground">Failed</dt>
                    <dd
                      className={cn(
                        'tabular text-right',
                        dashboard.data.jobs.failedLast24h > 0 && 'text-destructive',
                      )}
                    >
                      {dashboard.data.jobs.failedLast24h}
                    </dd>
                  </dl>
                </CardContent>
              </Card>

              <Card className="gap-0 py-0">
                <CardContent className="grid gap-2 px-5 py-4">
                  <Button asChild>
                    <Link to="/compose">Compose work</Link>
                  </Button>
                  <Button variant="outline" asChild>
                    <Link to="/accounts">Manage accounts</Link>
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>

          <Card className="gap-0 py-0">
            <CardHeader className="flex flex-row items-center justify-between border-b px-5 py-3">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Recent activity
              </CardTitle>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/logs">All logs</Link>
              </Button>
            </CardHeader>
            <CardContent className="px-0 py-0">
              {dashboard.data.recentActivity.length === 0 ? (
                <div className="p-5">
                  <EmptyState
                    title="Nothing has happened yet"
                    description="Import the roster and start a browser to see activity here."
                  />
                </div>
              ) : (
                <ul className="divide-y">
                  {dashboard.data.recentActivity.map((entry) => (
                    <li
                      key={entry.id}
                      className="grid grid-cols-[72px_1fr_auto] items-center gap-3 px-5 py-2.5 text-sm"
                    >
                      <LogLevelDot level={entry.level} />
                      <span className="truncate">{entry.message}</span>
                      <span className="text-xs whitespace-nowrap text-muted-foreground">
                        {relativeTime(entry.createdAt)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
};
