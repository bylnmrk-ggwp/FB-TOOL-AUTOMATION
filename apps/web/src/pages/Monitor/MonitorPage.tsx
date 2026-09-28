import type { ReactElement } from 'react';
import { AccountStatusBadge, JobStatusBadge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { EmptyState } from '../../components/ui/Feedback';
import { PageHeader } from '../../components/ui/PageHeader';
import { StatusDot, type StatusTone } from '../../components/ui/StatusDot';
import { useAccounts, useSessions } from '../../features/accounts/hooks';
import { useJobs } from '../../features/queue/hooks';
import { useLiveStore, type ConnectionState } from '../../features/automation/liveStore';
import { clockTime, humanise, relativeTime } from '../../lib/format';
import './MonitorPage.css';

const CONNECTION_TONE: Record<ConnectionState, StatusTone> = {
  connecting: 'warn',
  open: 'ok',
  closed: 'danger',
};

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  connecting: 'Connecting to the live feed',
  open: 'Live',
  closed: 'Disconnected — retrying',
};

/**
 * The page that is worth leaving open. Everything on it is driven by the
 * WebSocket: running jobs, the accounts they hold, and the raw event stream.
 */
export const MonitorPage = (): ReactElement => {
  const connection = useLiveStore((state) => state.connection);
  const progress = useLiveStore((state) => state.progress);
  const recent = useLiveStore((state) => state.recent);

  const sessions = useSessions();
  const accounts = useAccounts({ limit: 200 });
  const running = useJobs({ status: ['running', 'queued', 'retrying'], limit: 50 });

  const accountName = new Map(
    (accounts.data?.items ?? []).map((account) => [account.id, account.displayName]),
  );

  return (
    <div className="page">
      <PageHeader
        title="Monitor"
        description="Live state, pushed from the server as it happens."
        actions={
          <StatusDot tone={CONNECTION_TONE[connection]} label={CONNECTION_LABEL[connection]} />
        }
      />

      <div className="monitor__columns">
        <Card title="Running work">
          {(running.data?.items ?? []).length === 0 ? (
            <EmptyState title="Nothing is running" description="Queued work appears here." />
          ) : (
            <ul className="monitor__jobs">
              {(running.data?.items ?? []).map((job) => {
                const live = progress[job.id];
                const value = live?.progress ?? job.progress;

                return (
                  <li key={job.id} className="monitor__job">
                    <div className="monitor__job-head">
                      <span>{humanise(job.type)}</span>
                      <JobStatusBadge status={job.status} />
                    </div>
                    <p className="muted">{accountName.get(job.accountId) ?? job.accountId}</p>
                    <div className="monitor__bar">
                      <div className="monitor__bar-fill" style={{ width: `${value}%` }} />
                    </div>
                    <p className="monitor__step">{live?.step ?? 'Waiting for a worker'}</p>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card title="Browsers">
          {(sessions.data ?? []).length === 0 ? (
            <EmptyState
              title="No browser is open"
              description="Start one from the Accounts page."
            />
          ) : (
            <ul className="monitor__sessions">
              {(sessions.data ?? []).map((session) => (
                <li key={session.sessionId} className="monitor__session">
                  <div className="monitor__job-head">
                    <span>{accountName.get(session.accountId) ?? session.accountId}</span>
                    <AccountStatusBadge status={session.status} />
                  </div>
                  <p className="muted">
                    {session.headless ? 'Headless' : 'Visible'} · started{' '}
                    {relativeTime(session.startedAt)}
                  </p>
                  {session.currentUrl !== null && (
                    <p className="mono monitor__url">{session.currentUrl}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Event stream">
        {recent.length === 0 ? (
          <p className="muted">Waiting for the first event…</p>
        ) : (
          <ul className="monitor__events">
            {recent.slice(0, 60).map((event, index) => (
              <li key={`${event.timestamp}-${index}`} className="monitor__event">
                <span className="monitor__event-time">{clockTime(event.timestamp)}</span>
                <span className="monitor__event-type">{event.type}</span>
                <span className="monitor__event-detail">{describe(event)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
};

/** One readable line per event, without dumping the whole payload. */
const describe = (event: { type: string; payload: unknown }): string => {
  const payload = event.payload;
  if (typeof payload !== 'object' || payload === null) return '';

  const record = payload as Record<string, unknown>;
  const parts: string[] = [];

  if (typeof record['accountId'] === 'string') parts.push(record['accountId']);
  if (typeof record['jobId'] === 'string') parts.push(record['jobId']);
  if (typeof record['id'] === 'string') parts.push(record['id']);
  if (typeof record['status'] === 'string') parts.push(String(record['status']));
  if (typeof record['step'] === 'string') parts.push(String(record['step']));
  if (typeof record['message'] === 'string') parts.push(String(record['message']));

  return parts.join(' · ');
};
