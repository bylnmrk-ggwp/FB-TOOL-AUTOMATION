import { and, count, desc, eq, gte, inArray, like, lte } from 'drizzle-orm';
import type { LogEntry } from '@fb/shared';
import { nowIso } from '@fb/shared';
import type { LogFilter, LogRepository, NewLogEntry, Page } from '@fb/domain';
import type { Database } from '../db.js';
import { automationLogs } from '../schema/logs.js';
import { toLogEntry, toJsonColumn } from './mappers.js';

export class LogRepositoryImpl implements LogRepository {
  constructor(private readonly db: Database) {}

  async append(entry: NewLogEntry): Promise<LogEntry> {
    const createdAt = nowIso();
    await this.db.insert(automationLogs).values({
      id: entry.id,
      level: entry.level,
      message: entry.message,
      event: entry.event,
      accountId: entry.accountId,
      jobId: entry.jobId,
      sessionId: entry.sessionId,
      requestId: entry.requestId,
      context: entry.context === null ? null : toJsonColumn(entry.context),
      createdAt,
    });

    return {
      id: entry.id,
      level: entry.level,
      message: entry.message,
      event: entry.event,
      accountId: entry.accountId,
      jobId: entry.jobId,
      sessionId: entry.sessionId,
      requestId: entry.requestId,
      context: entry.context,
      createdAt,
    };
  }

  async list(filter: LogFilter): Promise<Page<LogEntry>> {
    const where = this.buildWhere(filter);

    const rows = await this.db
      .select()
      .from(automationLogs)
      .where(where)
      .orderBy(desc(automationLogs.createdAt))
      .limit(filter.limit)
      .offset(filter.offset);

    // Logs grow without bound, so the total is counted over the same filter
    // rather than the whole table.
    const totals = await this.db.select({ value: count() }).from(automationLogs).where(where);

    return {
      items: rows.map(toLogEntry),
      total: totals[0]?.value ?? 0,
      limit: filter.limit,
      offset: filter.offset,
    };
  }

  async recent(limit: number): Promise<LogEntry[]> {
    const rows = await this.db
      .select()
      .from(automationLogs)
      .orderBy(desc(automationLogs.createdAt))
      .limit(limit);
    return rows.map(toLogEntry);
  }

  async deleteOlderThan(cutoff: Date): Promise<number> {
    const iso = cutoff.toISOString();
    const doomed = await this.db
      .select({ id: automationLogs.id })
      .from(automationLogs)
      .where(lte(automationLogs.createdAt, iso));

    if (doomed.length === 0) return 0;
    await this.db.delete(automationLogs).where(lte(automationLogs.createdAt, iso));
    return doomed.length;
  }

  private buildWhere(filter: LogFilter) {
    const clauses = [];
    if (filter.level !== undefined && filter.level.length > 0) {
      clauses.push(inArray(automationLogs.level, [...filter.level]));
    }
    if (filter.accountId !== undefined)
      clauses.push(eq(automationLogs.accountId, filter.accountId));
    if (filter.jobId !== undefined) clauses.push(eq(automationLogs.jobId, filter.jobId));
    if (filter.event !== undefined) clauses.push(eq(automationLogs.event, filter.event));
    if (filter.search !== undefined) {
      clauses.push(like(automationLogs.message, `%${filter.search}%`));
    }
    if (filter.from !== undefined) {
      clauses.push(gte(automationLogs.createdAt, filter.from.toISOString()));
    }
    if (filter.to !== undefined)
      clauses.push(lte(automationLogs.createdAt, filter.to.toISOString()));
    return clauses.length === 0 ? undefined : and(...clauses);
  }
}
