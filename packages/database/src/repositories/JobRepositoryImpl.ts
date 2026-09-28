import { and, asc, count, desc, eq, gte, inArray, isNull, lte, notInArray, or } from 'drizzle-orm';
import type { Job, JobStatus, QueueStats } from '@fb/shared';
import { JOB_STATUSES, JobNotFoundError, nowIso } from '@fb/shared';
import type { ClaimRequest, JobFilter, JobPatch, JobRepository, NewJob, Page } from '@fb/domain';
import type { Database } from '../db.js';
import type { SqliteConnection } from '../connection.js';
import { jobs } from '../schema/jobs.js';
import { toJob, toJsonColumn } from './mappers.js';

const TERMINAL: readonly JobStatus[] = ['completed', 'failed', 'cancelled'];

export class JobRepositoryImpl implements JobRepository {
  constructor(
    private readonly db: Database,
    private readonly connection: SqliteConnection,
    /** Identifies this process in `locked_by`, so a restart can spot its own rows. */
    private readonly workerId: string,
  ) {}

  async create(job: NewJob): Promise<Job> {
    const [created] = await this.createMany([job]);
    if (created === undefined) throw new JobNotFoundError(job.id);
    return created;
  }

  async createMany(newJobs: readonly NewJob[]): Promise<Job[]> {
    if (newJobs.length === 0) return [];
    const now = nowIso();

    await this.db.insert(jobs).values(
      newJobs.map((job) => ({
        id: job.id,
        accountId: job.accountId,
        type: job.type,
        status: job.status,
        payload: toJsonColumn(job.payload),
        priority: job.priority,
        retryCount: 0,
        maxRetries: job.maxRetries,
        progress: 0,
        runAfter: job.runAfter,
        result: null,
        lastError: null,
        lockedBy: null,
        createdAt: now,
        queuedAt: null,
        startedAt: null,
        finishedAt: null,
        updatedAt: now,
      })),
    );

    return this.findAllByIds(newJobs.map((job) => job.id));
  }

  async findById(id: string): Promise<Job | null> {
    const rows = await this.db.select().from(jobs).where(eq(jobs.id, id)).limit(1);
    const row = rows[0];
    return row === undefined ? null : toJob(row);
  }

  async list(filter: JobFilter): Promise<Page<Job>> {
    const where = this.buildWhere(filter);

    const rows = await this.db
      .select()
      .from(jobs)
      .where(where)
      .orderBy(desc(jobs.createdAt))
      .limit(filter.limit)
      .offset(filter.offset);

    const totals = await this.db.select({ value: count() }).from(jobs).where(where);

    return {
      items: rows.map(toJob),
      total: totals[0]?.value ?? 0,
      limit: filter.limit,
      offset: filter.offset,
    };
  }

  async update(id: string, patch: JobPatch): Promise<Job> {
    const values: Record<string, unknown> = { updatedAt: nowIso() };
    if (patch.status !== undefined) values['status'] = patch.status;
    if (patch.progress !== undefined) values['progress'] = patch.progress;
    if (patch.retryCount !== undefined) values['retryCount'] = patch.retryCount;
    if (patch.runAfter !== undefined) values['runAfter'] = patch.runAfter;
    if (patch.result !== undefined) {
      values['result'] = patch.result === null ? null : toJsonColumn(patch.result);
    }
    if (patch.lastError !== undefined) {
      values['lastError'] = patch.lastError === null ? null : toJsonColumn(patch.lastError);
    }
    if (patch.queuedAt !== undefined) values['queuedAt'] = patch.queuedAt;
    if (patch.startedAt !== undefined) values['startedAt'] = patch.startedAt;
    if (patch.finishedAt !== undefined) values['finishedAt'] = patch.finishedAt;

    // A job that reaches a terminal state releases its worker claim.
    if (patch.status !== undefined && TERMINAL.includes(patch.status)) values['lockedBy'] = null;

    await this.db.update(jobs).set(values).where(eq(jobs.id, id));

    const job = await this.findById(id);
    if (job === null) throw new JobNotFoundError(id);
    return job;
  }

  /**
   * Selection and claim happen in one transaction: the rows this call returns
   * are already marked `queued` and stamped with this worker, so a second
   * worker reading at the same moment cannot see them as available.
   */
  async claimDueJobs(request: ClaimRequest): Promise<Job[]> {
    const now = request.now.toISOString();
    const busy = [...request.busyAccountIds];

    return this.connection.transaction(async () => {
      const candidates = await this.db
        .select()
        .from(jobs)
        .where(
          and(
            inArray(jobs.status, ['pending', 'retrying']),
            or(isNull(jobs.runAfter), lte(jobs.runAfter, now)),
            busy.length === 0 ? undefined : notInArray(jobs.accountId, busy),
          ),
        )
        .orderBy(desc(jobs.priority), asc(jobs.createdAt))
        .limit(request.limit);

      // One job per account per pass: a worker holds the account while it runs,
      // so claiming a second would only queue work behind itself.
      const seenAccounts = new Set(busy);
      const chosenIds: string[] = [];
      for (const candidate of candidates) {
        if (seenAccounts.has(candidate.accountId)) continue;
        seenAccounts.add(candidate.accountId);
        chosenIds.push(candidate.id);
      }

      if (chosenIds.length === 0) return [];

      await this.db
        .update(jobs)
        .set({ status: 'queued', queuedAt: now, updatedAt: now, lockedBy: this.workerId })
        .where(inArray(jobs.id, chosenIds));

      return this.findAllByIds(chosenIds);
    });
  }

  /**
   * Jobs the previous process was working on. `queued` counts too: a job
   * claimed but never started is just as abandoned as one left running.
   */
  async findStaleRunning(olderThan: Date): Promise<Job[]> {
    const cutoff = olderThan.toISOString();
    const rows = await this.db
      .select()
      .from(jobs)
      .where(
        and(
          inArray(jobs.status, ['running', 'queued']),
          or(isNull(jobs.startedAt), lte(jobs.updatedAt, cutoff)),
        ),
      );
    return rows.map(toJob);
  }

  async findByStatus(status: readonly JobStatus[]): Promise<Job[]> {
    if (status.length === 0) return [];
    const rows = await this.db
      .select()
      .from(jobs)
      .where(inArray(jobs.status, [...status]));
    return rows.map(toJob);
  }

  async countRunningByAccount(): Promise<Record<string, number>> {
    const rows = await this.db
      .select({ accountId: jobs.accountId, value: count() })
      .from(jobs)
      .where(inArray(jobs.status, ['running', 'queued']))
      .groupBy(jobs.accountId);

    return Object.fromEntries(rows.map((row) => [row.accountId, row.value]));
  }

  async stats(): Promise<QueueStats> {
    const rows = await this.db
      .select({ status: jobs.status, value: count() })
      .from(jobs)
      .groupBy(jobs.status);

    const stats = Object.fromEntries(JOB_STATUSES.map((status) => [status, 0])) as QueueStats;
    for (const row of rows) stats[row.status] = row.value;
    return stats;
  }

  async statsSince(since: Date): Promise<{ total: number; succeeded: number; failed: number }> {
    const rows = await this.db
      .select({ status: jobs.status, value: count() })
      .from(jobs)
      .where(gte(jobs.createdAt, since.toISOString()))
      .groupBy(jobs.status);

    let total = 0;
    let succeeded = 0;
    let failed = 0;
    for (const row of rows) {
      total += row.value;
      if (row.status === 'completed') succeeded += row.value;
      if (row.status === 'failed') failed += row.value;
    }
    return { total, succeeded, failed };
  }

  async deleteByAccount(accountId: string): Promise<number> {
    const doomed = await this.db
      .select({ id: jobs.id })
      .from(jobs)
      .where(eq(jobs.accountId, accountId));

    if (doomed.length === 0) return 0;
    await this.db.delete(jobs).where(eq(jobs.accountId, accountId));
    return doomed.length;
  }

  private async findAllByIds(ids: readonly string[]): Promise<Job[]> {
    if (ids.length === 0) return [];
    const rows = await this.db
      .select()
      .from(jobs)
      .where(inArray(jobs.id, [...ids]));
    return rows.map(toJob);
  }

  private buildWhere(filter: JobFilter) {
    const clauses = [];
    if (filter.status !== undefined && filter.status.length > 0) {
      clauses.push(inArray(jobs.status, [...filter.status]));
    }
    if (filter.accountId !== undefined) clauses.push(eq(jobs.accountId, filter.accountId));
    if (filter.type !== undefined) clauses.push(eq(jobs.type, filter.type));
    return clauses.length === 0 ? undefined : and(...clauses);
  }
}
