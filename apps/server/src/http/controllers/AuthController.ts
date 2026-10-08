import type { FastifyReply, FastifyRequest } from 'fastify';
import {
  AppError,
  AuthInvalidError,
  AuthRateLimitedError,
  ERROR_CODES,
  LoginRequestSchema,
  type AuthSession,
  type LoginResponse,
} from '@fb/shared';
import type { AppConfig } from '../../config/index.js';
import { bearerToken } from '../auth/guard.js';
import { passwordMatches } from '../auth/password.js';
import { LoginRateLimiter } from '../auth/rate-limit.js';
import { issueToken, tokenExpiry, verifyToken } from '../auth/tokens.js';
import { validateBody } from '../middleware/index.js';

/** The two routes the guard leaves open: a probe and the login itself. */
export class AuthController {
  constructor(
    private readonly auth: AppConfig['auth'],
    private readonly limiter: LoginRateLimiter = new LoginRateLimiter(),
    private readonly now: () => number = Date.now,
  ) {}

  session = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const token = bearerToken(request);
    const body: AuthSession =
      this.auth.password === null
        ? { authRequired: false, authenticated: true }
        : {
            authRequired: true,
            authenticated: token !== null && verifyToken(this.auth.secret, token, this.now()),
          };
    await reply.status(200).send(body);
  };

  login = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { password } = validateBody(LoginRequestSchema, request);
    const expected = this.auth.password;
    if (expected === null) {
      throw new AppError(ERROR_CODES.CONFLICT, 'Login is not configured on this server', {
        status: 409,
      });
    }

    const now = this.now();
    if (this.limiter.isLimited(now)) {
      throw new AuthRateLimitedError(Math.ceil(this.limiter.retryAfterMs(now) / 1000));
    }
    if (!passwordMatches(password, expected)) {
      this.limiter.recordFailure(now);
      throw new AuthInvalidError();
    }

    this.limiter.reset();
    const body: LoginResponse = {
      token: issueToken(this.auth.secret, now),
      expiresAt: tokenExpiry(now),
    };
    await reply.status(200).send(body);
  };
}
