import type { ReactElement, ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export const PageHeader = ({ title, description, actions }: PageHeaderProps): ReactElement => (
  <header className="flex flex-wrap items-start justify-between gap-4">
    <div className="space-y-1">
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      {description !== undefined && (
        <p className="max-w-prose text-sm text-muted-foreground">{description}</p>
      )}
    </div>
    {actions !== undefined && <div className="flex flex-wrap gap-2">{actions}</div>}
  </header>
);
