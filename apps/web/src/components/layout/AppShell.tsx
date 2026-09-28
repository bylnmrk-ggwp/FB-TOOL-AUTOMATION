import { useState, type ReactElement } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Activity,
  FileText,
  LayoutDashboard,
  ListOrdered,
  Menu,
  Moon,
  PenSquare,
  Settings,
  Sun,
  Users,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { cn } from '@/lib/utils';
import { NAV_ROUTES } from '../../app/routes';
import { useTheme } from '../../hooks/useTheme';
import { useLiveEvents } from '../../features/automation/useLiveEvents';
import { ConnectionBadge } from './ConnectionBadge';

const ICONS: Record<string, LucideIcon> = {
  '/': LayoutDashboard,
  '/accounts': Users,
  '/groups': UsersRound,
  '/compose': PenSquare,
  '/queue': ListOrdered,
  '/monitor': Activity,
  '/logs': FileText,
  '/settings': Settings,
};

const Navigation = ({ onNavigate }: { onNavigate?: () => void }): ReactElement => (
  <nav className="grid gap-0.5" aria-label="Main">
    {NAV_ROUTES.map((route) => {
      const Icon = ICONS[route.path] ?? LayoutDashboard;
      return (
        <NavLink
          key={route.path}
          to={route.path}
          end={route.path === '/'}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
              isActive && 'bg-sidebar-accent font-medium text-sidebar-accent-foreground',
            )
          }
        >
          <Icon className="size-4 shrink-0" aria-hidden="true" />
          {route.label}
        </NavLink>
      );
    })}
  </nav>
);

/**
 * The wordmark is drawn for a white ground; `mcarsph-logo-on-dark.png` is the
 * same mark with its black turned white and its background cleared, so it
 * sits straight on the black sidebar.
 */
const Brand = (): ReactElement => (
  <div className="grid gap-1.5 px-2.5">
    <img
      src="/mcarsph-logo-on-dark.png"
      alt="MCARSPH"
      width={381}
      height={132}
      className="h-auto w-full max-w-[170px]"
    />
    <span className="px-0.5 text-xs font-medium tracking-tight text-sidebar-foreground">
      FB Automation
    </span>
  </div>
);

export const AppShell = (): ReactElement => {
  const { theme, toggle } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const current = NAV_ROUTES.find((route) =>
    route.path === '/' ? location.pathname === '/' : location.pathname.startsWith(route.path),
  );

  // One socket for the whole application, opened where the application lives
  // rather than inside any one page.
  useLiveEvents();

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col gap-6 border-r bg-sidebar px-3 py-5 md:flex">
        <Brand />
        <Navigation />
        <p className="mt-auto px-2.5 text-xs text-muted-foreground">Version 0.1.0</p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur md:px-6">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 bg-sidebar px-3 py-5">
              <SheetTitle className="sr-only">Navigation</SheetTitle>
              <div className="grid gap-6">
                <Brand />
                <Navigation onNavigate={() => setMenuOpen(false)} />
              </div>
            </SheetContent>
          </Sheet>

          <span className="text-sm font-medium md:hidden">{current?.label ?? 'FB Automation'}</span>

          <div className="ml-auto flex items-center gap-3">
            <ConnectionBadge />
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {theme === 'dark' ? <Sun /> : <Moon />}
            </Button>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 md:px-6">
          <div className="mx-auto w-full max-w-[1280px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
};
