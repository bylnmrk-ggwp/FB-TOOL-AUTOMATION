import type { ReactElement } from 'react';
import { StatusDot, type StatusTone } from '../ui/StatusDot';
import { useHealth } from '../../hooks/useHealth';

/** Shows whether the browser can currently reach the API. */
export const ConnectionBadge = (): ReactElement => {
  const health = useHealth();

  if (health.isPending) return <StatusDot tone="idle" label="Connecting to API" />;
  if (health.isError) return <StatusDot tone="danger" label="API unreachable" />;

  const tone: StatusTone = health.data.status === 'ok' ? 'ok' : 'warn';
  const label = health.data.status === 'ok' ? 'API healthy' : 'API degraded';
  return <StatusDot tone={tone} label={label} />;
};
