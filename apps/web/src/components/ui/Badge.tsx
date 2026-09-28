import type { ReactElement } from 'react';
import type { AccountStatus, JobStatus, LogLevel } from '@fb/shared';
import './Badge.css';

export type BadgeTone = 'neutral' | 'info' | 'ok' | 'warn' | 'danger' | 'accent';

/** One mapping from a domain status to a colour, used by every table. */
const ACCOUNT_TONES: Record<AccountStatus, BadgeTone> = {
  offline: 'neutral',
  starting: 'info',
  online: 'ok',
  busy: 'accent',
  stopping: 'warn',
  error: 'danger',
};

const JOB_TONES: Record<JobStatus, BadgeTone> = {
  pending: 'neutral',
  queued: 'info',
  running: 'accent',
  retrying: 'warn',
  completed: 'ok',
  failed: 'danger',
  cancelled: 'neutral',
};

const LEVEL_TONES: Record<LogLevel, BadgeTone> = {
  debug: 'neutral',
  info: 'info',
  warn: 'warn',
  error: 'danger',
};

export const Badge = ({ tone, label }: { tone: BadgeTone; label: string }): ReactElement => (
  <span className={`badge badge--${tone}`}>{label}</span>
);

export const AccountStatusBadge = ({ status }: { status: AccountStatus }): ReactElement => (
  <Badge tone={ACCOUNT_TONES[status]} label={status} />
);

export const JobStatusBadge = ({ status }: { status: JobStatus }): ReactElement => (
  <Badge tone={JOB_TONES[status]} label={status} />
);

export const LogLevelBadge = ({ level }: { level: LogLevel }): ReactElement => (
  <Badge tone={LEVEL_TONES[level]} label={level} />
);
