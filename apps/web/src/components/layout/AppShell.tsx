import type { ReactElement } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { NAV_ROUTES } from '../../app/routes';
import { useTheme } from '../../hooks/useTheme';
import { ConnectionBadge } from './ConnectionBadge';
import './AppShell.css';

export const AppShell = (): ReactElement => {
  const { theme, toggle } = useTheme();

  return (
    <div className="shell">
      <aside className="shell__sidebar">
        <div className="shell__brand">
          <span className="shell__brand-mark">FB</span>
          Automation
        </div>

        <nav className="shell__nav" aria-label="Main">
          {NAV_ROUTES.map((route) => (
            <NavLink key={route.path} to={route.path} end className="shell__nav-link">
              <span aria-hidden="true">{route.glyph}</span>
              {route.label}
            </NavLink>
          ))}
        </nav>

        <div className="shell__footer">v0.1.0</div>
      </aside>

      <div className="shell__main">
        <header className="shell__header">
          <ConnectionBadge />
          <button type="button" className="shell__theme" onClick={toggle}>
            {theme === 'dark' ? 'Light theme' : 'Dark theme'}
          </button>
        </header>
        <main className="shell__content">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
