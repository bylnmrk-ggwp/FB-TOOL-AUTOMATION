import type { ReactElement } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  AccountStatusDot,
  JobStatusDot,
  StatusDot,
  type StatusTone,
} from '@/components/common/StatusDot';
import { EmptyState } from '@/components/common/Feedback';
import { PageHeader } from '@/components/common/PageHeader';
import { useAllAccounts, useSessions } from '../../features/accounts/hooks';
import { OperatorPrompts } from '../../features/monitoring/components/OperatorPrompts';
import { useJobs } from '../../features/queue/hooks';
import { useLiveStore, type ConnectionState } from '../../features/automation/liveStore';
import { clockTime, humanise, relativeTime } from '../../lib/format';

const CONNECTION: Record<ConnectionState, { tone: StatusTone; label: string }> = {
  connecting: { tone: 'warn', label: 'Connecting to the live feed' },
  open: { tone: 'ok', label: 'Live' },
  closed: { tone: 'danger', label: 'Disconnected — reconnecting' },
};

const Panel = ({ title, children }: { title: string; children: ReactElement }): ReactElement => (
  <Card className="gap-0 py-0">
    <CardHeader className="border-b px-5 py-3">
      <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
    </CardHeader>
    <CardContent className="px-0 py-0">{children}</CardContent>
  </Card>
);

/**
 * The page worth leaving open. Everything on it is driven by the WebSocket:
 * jobs waiting for a person, running jobs, the browsers they hold, and the
 * raw event stream.
 */
export const MonitorPage = (): ReactElement => {
  const connection = useLiveStore((state) => state.connection);
  const progress = useLiveStore((state) => state.progress);
  const recent = useLiveStore((state) => state.recent);

  const sessions = useSessions();
  const accounts = useAllAccounts();
  const running = useJobs({ status: ['running', 'queued', 'retrying'], limit: 50 });

  const names = new Map((accounts.data ?? []).map((account) => [account.id, account.displayName]));
  const accountName = (id: string): string => names.get(id) ?? id;

  const activeJobs = running.data?.items ?? [];
  const openSessions = sessions.data ?? [];

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Monitor"
        description="Live state, pushed from the server as it happens."
        actions={
          <StatusDot
            tone={CONNECTION[connection].tone}
            label={CONNECTION[connection].label}
            pulse={connection !== 'open'}
          />
        }
      />

      <OperatorPrompts accountName={accountName} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={`Running work (${activeJobs.length})`}>
          {activeJobs.length === 0 ? (
            <div className="p-4">
              <EmptyState title="Nothing is running" description="Queued work appears here." />
            </div>
          ) : (
            <ul className="divide-y">
              {activeJobs.map((job) => {
                const live = progress[job.id];
                const value = live?.progress ?? job.progress;
                return (
                  <li key={job.id} className="grid gap-2 px-5 py-3">
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="font-medium">{humanise(job.type)}</span>
                      <JobStatusDot status={job.status} />
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {accountName(job.accountId)}
                    </span>
                    <Progress value={value} className="h-1.5" />
                    <span className="text-xs text-muted-foreground">
                      {live?.step ?? 'Waiting for a worker'}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        <Panel title={`Browsers (${openSessions.length})`}>
          {openSessions.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title="No browser is open"
                description="Start one from the Accounts page."
              />
            </div>
          ) : (
            <ul className="divide-y">
              {openSessions.map((session) => (
                <li key={session.sessionId} className="grid gap-1 px-5 py-3">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-medium">{accountName(session.accountId)}</span>
                    <AccountStatusDot status={session.status} />
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {session.headless ? 'Headless' : 'Visible window'}, started{' '}
                    {relativeTime(session.startedAt)}
                  </span>
                  {session.currentUrl !== null && (
                    <span className="truncate font-mono text-xs text-muted-foreground">
                      {session.currentUrl}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Event stream">
        {recent.length === 0 ? (
          <p className="px-5 py-4 text-sm text-muted-foreground">Waiting for the first event.</p>
        ) : (
          <ScrollArea className="h-[420px]">
            <ul className="divide-y font-mono text-xs">
              {recent.slice(0, 100).map((event, index) => (
                <li
                  key={`${event.timestamp}-${index}`}
                  className="grid grid-cols-[80px_1fr] gap-3 px-5 py-2 sm:grid-cols-[80px_200px_1fr]"
                >
                  <span className="text-muted-foreground">{clockTime(event.timestamp)}</span>
                  <span className="text-primary">{event.type}</span>
                  <span className="col-span-2 truncate text-muted-foreground sm:col-span-1">
                    {describe(event)}
                  </span>
                </li>
              ))}
            </ul>
          </ScrollArea>
        )}
      </Panel>
    </div>
  );
};

/** One readable line per event, without dumping the whole payload. */
const describe = (event: { type: string; payload: unknown }): string => {
  const payload = event.payload;
  if (typeof payload !== 'object' || payload === null) return '';

  const record = payload as Record<string, unknown>;
  const parts: string[] = [];
  for (const key of ['accountId', 'jobId', 'id', 'status', 'step', 'message']) {
    const value = record[key];
    if (typeof value === 'string') parts.push(value);
  }
  return parts.join('  ');
};
