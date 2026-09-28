import type { ReactElement } from 'react';
import type { AccountStatus, JobStatus, LoginStatus, LogLevel } from '@fb/shared';
import { cn } from '@/lib/utils';

export type StatusTone = 'ok' | 'warn' | 'danger' | 'info' | 'idle' | 'active';

const DOT: Record<StatusTone, string> = {
  ok: 'bg-success',
  warn: 'bg-warning',
  danger: 'bg-destructive',
  info: 'bg-info',
  idle: 'bg-muted-foreground/50',
  active: 'bg-primary',
};

/**
 * The one status vocabulary for the whole interface: a coloured dot and a
 * sentence-case word. Colour is never the only carrier — the word is always
 * there — and the same tone means the same thing on every page.
 */
export const StatusDot = ({
  tone,
  label,
  pulse = false,
  className,
}: {
  tone: StatusTone;
  label: string;
  /** Only for states that are actively changing, so motion stays meaningful. */
  pulse?: boolean;
  className?: string;
}): ReactElement => (
  <span className={cn('inline-flex items-center gap-2 text-sm', className)}>
    <span className="relative flex size-2">
      {pulse && (
        <span
          className={cn(
            'absolute inline-flex size-full animate-ping rounded-full opacity-60',
            DOT[tone],
          )}
          aria-hidden="true"
        />
      )}
      <span
        className={cn('relative inline-flex size-2 rounded-full', DOT[tone])}
        aria-hidden="true"
      />
    </span>
    <span>{label}</span>
  </span>
);

const ACCOUNT_TONES: Record<AccountStatus, StatusTone> = {
  offline: 'idle',
  starting: 'info',
  online: 'ok',
  busy: 'active',
  stopping: 'warn',
  error: 'danger',
};

const JOB_TONES: Record<JobStatus, StatusTone> = {
  pending: 'idle',
  queued: 'info',
  running: 'active',
  retrying: 'warn',
  completed: 'ok',
  failed: 'danger',
  cancelled: 'idle',
};

const LEVEL_TONES: Record<LogLevel, StatusTone> = {
  debug: 'idle',
  info: 'info',
  warn: 'warn',
  error: 'danger',
};

const LOGIN_TONES: Record<LoginStatus, StatusTone> = {
  unknown: 'idle',
  logged_in: 'ok',
  logged_out: 'warn',
  checkpoint: 'danger',
  two_factor: 'danger',
  email_confirmation: 'danger',
  captcha: 'danger',
  disabled: 'danger',
  restricted: 'warn',
};

export const LOGIN_LABELS: Record<LoginStatus, string> = {
  unknown: 'Not checked',
  logged_in: 'Logged in',
  logged_out: 'Logged out',
  checkpoint: 'Checkpoint',
  two_factor: 'Needs 2FA',
  email_confirmation: 'Confirm email',
  captcha: 'Captcha',
  disabled: 'Disabled',
  restricted: 'Restricted',
};

export const LoginStatusDot = ({ status }: { status: LoginStatus }): ReactElement => (
  <StatusDot tone={LOGIN_TONES[status]} label={LOGIN_LABELS[status]} />
);

/** "logged_out" reads as "Logged out": one vocabulary, sentence case, no snake case. */
const sentence = (value: string): string => {
  const words = value.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
};

const MOVING: ReadonlySet<string> = new Set(['starting', 'busy', 'stopping', 'running']);

export const AccountStatusDot = ({ status }: { status: AccountStatus }): ReactElement => (
  <StatusDot tone={ACCOUNT_TONES[status]} label={sentence(status)} pulse={MOVING.has(status)} />
);

export const JobStatusDot = ({ status }: { status: JobStatus }): ReactElement => (
  <StatusDot tone={JOB_TONES[status]} label={sentence(status)} pulse={MOVING.has(status)} />
);

export const LogLevelDot = ({ level }: { level: LogLevel }): ReactElement => (
  <StatusDot tone={LEVEL_TONES[level]} label={level} />
);
