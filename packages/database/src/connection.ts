import { AsyncLocalStorage } from 'node:async_hooks';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync, type StatementSync } from 'node:sqlite';

export type QueryMethod = 'run' | 'all' | 'get' | 'values';

/**
 * Thin wrapper over the SQLite database built into Node. It is used instead of
 * a native addon so a clean checkout needs no compiler toolchain — which is
 * also what keeps Python out of the install.
 *
 * SQLite itself is synchronous. The async surface exists because Drizzle's
 * proxy driver expects promises, and because serialising access through one
 * queue is what makes `transaction()` safe when several requests overlap.
 */
export class SqliteConnection {
  private readonly db: DatabaseSync;
  private readonly statements = new Map<string, StatementSync>();
  private readonly inTransaction = new AsyncLocalStorage<true>();
  private queue: Promise<unknown> = Promise.resolve();
  private closed = false;

  constructor(private readonly file: string) {
    if (file !== ':memory:') mkdirSync(dirname(file), { recursive: true });
    this.db = new DatabaseSync(file);

    // WAL lets the queue read while a worker writes; NORMAL is the usual
    // durability trade for WAL and is safe against process crashes.
    this.db.exec('PRAGMA journal_mode = WAL');
    this.db.exec('PRAGMA synchronous = NORMAL');
    this.db.exec('PRAGMA foreign_keys = ON');
    // Generous, because a busy wait is cheaper than a failed write when
    // several workers commit at once.
    this.db.exec('PRAGMA busy_timeout = 15000');
  }

  get path(): string {
    return this.file;
  }

  /** Runs one statement. Results come back as value arrays, as Drizzle wants. */
  async query(sql: string, params: readonly unknown[], method: QueryMethod): Promise<unknown[][]> {
    return this.inTransaction.getStore() === true
      ? this.executeNow(sql, params, method)
      : this.serialise(() => this.executeNow(sql, params, method));
  }

  /**
   * Runs `fn` inside `BEGIN IMMEDIATE`. Every statement issued by `fn` joins
   * the transaction, and nothing else can interleave with it.
   */
  async transaction<T>(fn: () => Promise<T>): Promise<T> {
    return this.serialise(() =>
      this.inTransaction.run(true, async () => {
        this.db.exec('BEGIN IMMEDIATE');
        try {
          const result = await fn();
          this.db.exec('COMMIT');
          return result;
        } catch (error) {
          // The original error is what the caller must see. A ROLLBACK that
          // itself throws — because BEGIN never took, or COMMIT already ran —
          // must not replace it, and above all must not escape unhandled and
          // kill the process, which is what a bare ROLLBACK here once did
          // under concurrent load.
          try {
            this.db.exec('ROLLBACK');
          } catch {
            // No transaction was active; nothing to undo.
          }
          throw error;
        }
      }),
    );
  }

  exec(sql: string): void {
    this.db.exec(sql);
  }

  /** Synchronous write used by the migration runner. */
  runSync(sql: string, ...params: readonly unknown[]): void {
    this.prepare(sql).run(...(params as never[]));
  }

  /** Synchronous read used by the migration runner, which runs before Drizzle. */
  allSync<T>(sql: string, ...params: readonly unknown[]): T[] {
    return this.prepare(sql).all(...(params as never[])) as T[];
  }

  isHealthy(): boolean {
    if (this.closed) return false;
    try {
      this.db.prepare('SELECT 1').get();
      return true;
    } catch {
      return false;
    }
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.statements.clear();
    this.db.close();
  }

  private executeNow(
    sql: string,
    params: readonly unknown[],
    method: QueryMethod,
  ): Promise<unknown[][]> {
    const statement = this.prepare(sql);
    const values = params as never[];

    if (method === 'run') {
      statement.run(...values);
      return Promise.resolve([]);
    }

    if (method === 'get') {
      const row = statement.get(...values);
      return Promise.resolve(row === undefined ? [] : [Object.values(row)]);
    }

    const rows = statement.all(...values);
    return Promise.resolve(rows.map((row) => Object.values(row)));
  }

  /** Statements are reused: preparing the same SQL per call is pure overhead. */
  private prepare(sql: string): StatementSync {
    const cached = this.statements.get(sql);
    if (cached !== undefined) return cached;

    const statement = this.db.prepare(sql);
    this.statements.set(sql, statement);
    return statement;
  }

  private serialise<T>(fn: () => Promise<T>): Promise<T> {
    const result = this.queue.then(fn, fn);
    // Swallow here only so one failed query cannot break the chain for the next.
    this.queue = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
}
