import type { ReactElement, ReactNode } from 'react';
import './Card.css';

interface CardProps {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export const Card = ({ title, actions, children }: CardProps): ReactElement => (
  <section className="card">
    {(title !== undefined || actions !== undefined) && (
      <header className="card__header">
        {title !== undefined && <h2 className="card__title">{title}</h2>}
        {actions}
      </header>
    )}
    <div className="card__body">{children}</div>
  </section>
);
