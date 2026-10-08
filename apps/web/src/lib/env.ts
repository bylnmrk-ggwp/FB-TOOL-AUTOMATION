import { normaliseApiBase } from './api-base';

/**
 * Vite inlines these at build time. Reading them in one module keeps
 * import.meta.env out of the rest of the app.
 */
export const WEB_CONFIG = {
  /**
   * Same-origin by default: the dev server proxies /api to the backend and
   * the API serves the built app itself. A static host such as Vercel sets
   * VITE_PUBLIC_API_URL to the API's public origin at build time.
   */
  apiBaseUrl: normaliseApiBase(import.meta.env['VITE_PUBLIC_API_URL']),
  isDev: import.meta.env.DEV,
} as const;
