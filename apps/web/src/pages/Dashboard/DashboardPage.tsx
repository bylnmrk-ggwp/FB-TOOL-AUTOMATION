import type { ReactElement } from 'react';
import { Card } from '../../components/ui/Card';
import { StatusDot, type StatusTone } from '../../components/ui/StatusDot';
import { useHealth } from '../../hooks/useHealth';
import './DashboardPage.css';

const toneFor = (state: 'up' | 'down'): StatusTone => (state === 'up' ? 'ok' : 'danger');

export const DashboardPage = (): ReactElement => {
  const health = useHealth();

  return (
    <div className="dashboard">
      <header className="dashboard__head">
        <h1 className="dashboard__title">Dashboard</h1>
        <p className="dashboard__subtitle">System status reported by the automation API.</p>
      </header>

      <Card title="API health">
        {health.isPending && <p className="dashboard__muted">Contacting the API…</p>}

        {health.isError && (
          <p className="dashboard__error">
            The API did not answer. Start it with <code>pnpm dev:server</code>.
          </p>
        )}

        {health.isSuccess && (
          <dl className="dashboard__grid">
            <div>
              <dt>Status</dt>
              <dd>
                <StatusDot
                  tone={health.data.status === 'ok' ? 'ok' : 'warn'}
                  label={health.data.status}
                />
              </dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{health.data.version}</dd>
            </div>
            <div>
              <dt>Uptime</dt>
              <dd>{health.data.uptimeSeconds}s</dd>
            </div>
            <div>
              <dt>Database</dt>
              <dd>
                <StatusDot
                  tone={toneFor(health.data.checks.database)}
                  label={health.data.checks.database}
                />
              </dd>
            </div>
            <div>
              <dt>Queue</dt>
              <dd>
                <StatusDot
                  tone={toneFor(health.data.checks.queue)}
                  label={health.data.checks.queue}
                />
              </dd>
            </div>
          </dl>
        )}
      </Card>
    </div>
  );
};
