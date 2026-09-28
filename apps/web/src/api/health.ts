import { HealthSchema, type Health } from '@fb/shared';
import { apiRequest } from './client';

export const fetchHealth = (signal?: AbortSignal): Promise<Health> =>
  apiRequest('/health', HealthSchema, { signal });
