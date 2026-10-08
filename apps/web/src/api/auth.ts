import {
  AuthSessionSchema,
  LoginResponseSchema,
  type AuthSession,
  type LoginResponse,
} from '@fb/shared';
import { apiRequest } from './client';

export const getSession = (signal?: AbortSignal): Promise<AuthSession> =>
  apiRequest('/auth/session', AuthSessionSchema, { signal });

export const login = (password: string): Promise<LoginResponse> =>
  apiRequest('/auth/login', LoginResponseSchema, { method: 'POST', body: { password } });
