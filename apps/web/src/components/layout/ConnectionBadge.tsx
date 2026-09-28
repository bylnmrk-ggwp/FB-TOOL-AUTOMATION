import type { ReactElement } from 'react';
import { StatusDot, type StatusTone } from '../ui/StatusDot';
import { useHealth } from '../../hooks/useHealth';
import { useLiveStore } from '../../features/automation/liveStore';

/**
 * Two signals in one place: whether the API answers, and whether the live feed
 * is attached. They fail independently, and the difference matters when
 * something looks stale.
 */
export const ConnectionBadge = (): ReactElement => {
  const health = useHealth();
  const connection = useLiveStore((state) => state.connection);

  if (health.isPending) return <StatusDot tone="idle" label="Connecting to the API" />;
  if (health.isError) return <StatusDot tone="danger" label="API unreachable" />;

  if (connection !== 'open') {
    return <StatusDot tone="warn" label="Live updates disconnected" />;
  }

  const tone: StatusTone = health.data.status === 'ok' ? 'ok' : 'warn';
  const label = health.data.status === 'ok' ? 'Connected' : 'API degraded';
  return <StatusDot tone={tone} label={label} />;
};
