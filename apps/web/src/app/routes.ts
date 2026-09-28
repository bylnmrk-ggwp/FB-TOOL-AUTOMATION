/**
 * Single registry for navigation and routing. A page is added here once and
 * appears in both the sidebar and the router.
 */
export interface RouteDescriptor {
  path: string;
  label: string;
  /** Short glyph used in the sidebar; replaced by an icon set later. */
  glyph: string;
}

export const NAV_ROUTES: readonly RouteDescriptor[] = [
  { path: '/', label: 'Dashboard', glyph: '◆' },
];
