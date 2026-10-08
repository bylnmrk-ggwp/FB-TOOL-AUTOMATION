import { z } from 'zod';
import { IsoDateTimeSchema } from './common.js';

export const LoginRequestSchema = z.object({
  password: z.string().min(1).max(256),
});
export type LoginRequest = z.infer<typeof LoginRequestSchema>;

export const LoginResponseSchema = z.object({
  token: z.string().min(1),
  expiresAt: IsoDateTimeSchema,
});
export type LoginResponse = z.infer<typeof LoginResponseSchema>;

/**
 * What the panel asks before it decides between the login page and the app.
 * `authenticated` reflects the bearer token on the probe itself, so a stored
 * token is validated in the same round trip.
 */
export const AuthSessionSchema = z.object({
  authRequired: z.boolean(),
  authenticated: z.boolean(),
});
export type AuthSession = z.infer<typeof AuthSessionSchema>;
