import type { FastifyInstance, FastifyRequest } from 'fastify';
import { API_PREFIX, AuthRequiredError, WEBSOCKET_PATH } from '@fb/shared';
import type { AppConfig } from '../../config/index.js';
import { verifyToken } from './tokens.js';

const BEARER = /^Bearer\s+(\S+)$/;

/** The token from `Authorization: Bearer …`, or null when absent or malformed. */
export const bearerToken = (request: FastifyRequest): string | null => {
  const header = request.headers.authorization;
  if (typeof header !== 'string') return null;
  const match = BEARER.exec(header);
  return match?.[1] ?? null;
};

/** Browsers cannot set headers on a WebSocket, so the socket carries `?token=`. */
const queryToken = (request: FastifyRequest): string | null => {
  const query = request.query as Record<string, unknown> | undefined;
  const token = query?.['token'];
  return typeof token === 'string' && token.length > 0 ? token : null;
};

const pathOf = (url: string): string => url.split('?')[0] ?? url;

/**
 * Every `/api/v1/*` route and the `/ws` upgrade need a valid token. Health,
 * the auth routes, CORS preflights and the static page stay open, so a phone
 * can load the panel and reach the login screen before it has a token.
 *
 * When the config has no password the hook is not installed at all.
 */
export const registerAuthGuard = (app: FastifyInstance, auth: AppConfig['auth']): void => {
  if (auth.password === null) return;

  app.addHook('onRequest', (request, _reply, done) => {
    if (request.method === 'OPTIONS') return done();

    const path = pathOf(request.url);
    const isSocket = path === WEBSOCKET_PATH;
    if (!isSocket && !path.startsWith(`${API_PREFIX}/`)) return done();
    if (path === `${API_PREFIX}/health` || path.startsWith(`${API_PREFIX}/auth/`)) return done();

    const token = isSocket ? queryToken(request) : bearerToken(request);
    if (token !== null && verifyToken(auth.secret, token, Date.now())) return done();

    return done(new AuthRequiredError());
  });
};
