import type { ReactElement, ReactNode } from 'react';
import './PageHeader.css';

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
}

export const PageHeader = ({ title, description, actions }: PageHeaderProps): ReactElement => (
  <header className="page-header">
    <div>
      <h1 className="page-header__title">{title}</h1>
      {description !== undefined && <p className="page-header__description">{description}</p>}
    </div>
    {actions !== undefined && <div className="page-header__actions">{actions}</div>}
  </header>
);
