/**
 * Vite inlines these at build time. Reading them in one module keeps
 * import.meta.env out of the rest of the app.
 */
export const WEB_CONFIG = {
  /** Same-origin by default: the dev server proxies /api to the backend. */
  apiBaseUrl: import.meta.env['VITE_API_URL'] ?? '',
  isDev: import.meta.env.DEV,
} as const;
