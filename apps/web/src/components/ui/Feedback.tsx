import type { ReactElement, ReactNode } from 'react';
import { AppError } from '@fb/shared';
import './Feedback.css';

/** Turns any thrown value into something worth showing a person. */
export const errorMessage = (error: unknown): string => {
  if (error instanceof AppError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong';
};

export const ErrorNotice = ({ error }: { error: unknown }): ReactElement => (
  <p className="notice notice--error" role="alert">
    {errorMessage(error)}
  </p>
);

export const InfoNotice = ({ children }: { children: ReactNode }): ReactElement => (
  <p className="notice notice--info">{children}</p>
);

export const Loading = ({ label = 'Loading…' }: { label?: string }): ReactElement => (
  <p className="notice notice--muted">{label}</p>
);

export const EmptyState = ({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}): ReactElement => (
  <div className="empty">
    <p className="empty__title">{title}</p>
    {description !== undefined && <p className="empty__description">{description}</p>}
    {action !== undefined && <div className="empty__action">{action}</div>}
  </div>
);
