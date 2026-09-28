import type { ReactElement } from 'react';
import './StatusDot.css';

export type StatusTone = 'ok' | 'warn' | 'danger' | 'info' | 'idle';

export const StatusDot = ({ tone, label }: { tone: StatusTone; label: string }): ReactElement => (
  <span className="status">
    <span className={`status__dot status__dot--${tone}`} aria-hidden="true" />
    {label}
  </span>
);
