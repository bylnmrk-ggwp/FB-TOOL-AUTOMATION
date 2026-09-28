import { drizzle, type SqliteRemoteDatabase } from 'drizzle-orm/sqlite-proxy';
import { SqliteConnection } from './connection.js';
import * as schema from './schema/index.js';

export type Database = SqliteRemoteDatabase<typeof schema>;

export interface DatabaseHandle {
  db: Database;
  connection: SqliteConnection;
  close: () => void;
}

/**
 * Binds Drizzle's query builder to the Node SQLite connection. Drizzle builds
 * the SQL; the connection executes it. Nothing else in the system opens a
 * database handle.
 */
export const createDatabase = (file: string): DatabaseHandle => {
  const connection = new SqliteConnection(file);

  const db = drizzle<typeof schema>(
    async (sql, params, method) => ({ rows: await connection.query(sql, params, method) }),
    { schema },
  );

  return { db, connection, close: () => connection.close() };
};

export { SqliteConnection };
export * as schema from './schema/index.js';
