import {
  DashboardStatsSchema,
  LogEntrySchema,
  MediaRefSchema,
  paginatedSchema,
  SettingsSchema,
  SystemPathsSchema,
  type DashboardStats,
  type ListLogsQuery,
  type LogEntry,
  type MediaRef,
  type Paginated,
  type Settings,
  type SystemPaths,
  type UpdateSettingsInput,
} from '@fb/shared';
import { API_PREFIX } from '@fb/shared';
import { apiRequest } from './client';
import { authHeaders } from '../lib/auth';
import { WEB_CONFIG } from '../lib/env';

const LogPageSchema = paginatedSchema(LogEntrySchema);

export const listLogs = (
  query: Partial<ListLogsQuery>,
  signal?: AbortSignal,
): Promise<Paginated<LogEntry>> =>
  apiRequest('/logs', LogPageSchema, {
    signal,
    query: {
      limit: query.limit ?? 100,
      offset: query.offset ?? 0,
      level: query.level === undefined ? undefined : [...query.level],
      accountId: query.accountId,
      jobId: query.jobId,
      search: query.search,
      from: query.from,
      to: query.to,
    },
  });

export const getDashboard = (signal?: AbortSignal): Promise<DashboardStats> =>
  apiRequest('/dashboard', DashboardStatsSchema, { signal });

export const getSettings = (signal?: AbortSignal): Promise<Settings> =>
  apiRequest('/settings', SettingsSchema, { signal });

export const updateSettings = (patch: UpdateSettingsInput): Promise<Settings> =>
  apiRequest('/settings', SettingsSchema, { method: 'PATCH', body: patch });

export const getSystemPaths = (signal?: AbortSignal): Promise<SystemPaths> =>
  apiRequest('/settings/paths', SystemPathsSchema, { signal });

/**
 * Uploads go through fetch directly rather than the JSON client: the body is
 * multipart, and the browser has to set its own boundary header.
 */
export const uploadMedia = async (file: File): Promise<MediaRef> => {
  const body = new FormData();
  body.append('file', file);

  const response = await fetch(`${WEB_CONFIG.apiBaseUrl}${API_PREFIX}/media`, {
    method: 'POST',
    headers: authHeaders(),
    body,
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      typeof payload === 'object' && payload !== null && 'error' in payload
        ? String((payload as { error: { message?: string } }).error.message)
        : `Upload failed with ${response.status}`;
    throw new Error(message);
  }

  return MediaRefSchema.parse(payload);
};
