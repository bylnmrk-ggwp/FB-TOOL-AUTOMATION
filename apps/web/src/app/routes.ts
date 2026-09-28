/**
 * Single registry for navigation and routing. A page is added here once and
 * appears in both the sidebar and the router.
 */
export interface RouteDescriptor {
  path: string;
  label: string;
}

export const NAV_ROUTES: readonly RouteDescriptor[] = [
  { path: '/', label: 'Dashboard' },
  { path: '/accounts', label: 'Accounts' },
  { path: '/groups', label: 'Groups' },
  { path: '/compose', label: 'Compose' },
  { path: '/queue', label: 'Queue' },
  { path: '/monitor', label: 'Monitor' },
  { path: '/logs', label: 'Logs' },
  { path: '/settings', label: 'Settings' },
];
