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

/**
 * Every `/api/v1/*` route and the `/ws` upgrade need a valid token. Health,
 * the auth routes, CORS preflights and the static page stay open, so a phone
 * can load the panel and reach the login screen before it has a token.
 *
 * The decision is made on the route the router picked, never on the text of
 * the request target. The router rewrites a target before it matches —
 * `http://host/api/v1/accounts` and `/%61pi/v1/accounts` both reach the
 * accounts handler — so a check on `request.url` would let those through.
 *
 * When the config has no password the hook is not installed at all.
 */
export const registerAuthGuard = (app: FastifyInstance, auth: AppConfig['auth']): void => {
  if (auth.password === null) return;

  app.addHook('onRequest', (request, _reply, done) => {
    // The matched route as a pattern, e.g. `/api/v1/accounts/:id`. Undefined
    // means no route matched and the 404 handler is about to answer.
    const route = request.routeOptions.url;
    if (route === undefined) return done();

    const isSocket = route === WEBSOCKET_PATH;
    if (!isSocket && !route.startsWith(`${API_PREFIX}/`)) return done();
    if (route === `${API_PREFIX}/health` || route.startsWith(`${API_PREFIX}/auth/`)) return done();

    const token = isSocket ? queryToken(request) : bearerToken(request);
    if (token !== null && verifyToken(auth.secret, token, Date.now())) return done();

    return done(new AuthRequiredError());
  });
};
