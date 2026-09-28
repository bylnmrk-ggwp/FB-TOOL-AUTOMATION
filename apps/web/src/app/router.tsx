import { createBrowserRouter, type RouteObject } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { DashboardPage } from '../pages/Dashboard';
import { AccountsPage } from '../pages/Accounts';
import { ComposePage } from '../pages/Compose';
import { QueuePage } from '../pages/Queue';
import { MonitorPage } from '../pages/Monitor';
import { LogsPage } from '../pages/Logs';
import { SettingsPage } from '../pages/Settings';
import { NotFoundPage } from '../pages/NotFoundPage';

const routes: RouteObject[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'accounts', element: <AccountsPage /> },
      { path: 'compose', element: <ComposePage /> },
      { path: 'queue', element: <QueuePage /> },
      { path: 'monitor', element: <MonitorPage /> },
      { path: 'logs', element: <LogsPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
