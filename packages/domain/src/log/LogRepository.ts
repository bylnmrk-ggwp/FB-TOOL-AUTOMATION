import type { LogEntry, LogLevel } from '@fb/shared';
import type { Page, PageRequest } from '../shared/index.js';

export interface NewLogEntry {
  id: string;
  level: LogLevel;
  message: string;
  event: string | null;
  accountId: string | null;
  jobId: string | null;
  sessionId: string | null;
  requestId: string | null;
  context: Record<string, unknown> | null;
}

export interface LogFilter extends PageRequest {
  level?: readonly LogLevel[];
  accountId?: string;
  jobId?: string;
  event?: string;
  search?: string;
  from?: Date;
  to?: Date;
}

export interface LogRepository {
  append(entry: NewLogEntry): Promise<LogEntry>;
  list(filter: LogFilter): Promise<Page<LogEntry>>;
  recent(limit: number): Promise<LogEntry[]>;
  deleteOlderThan(cutoff: Date): Promise<number>;
}
