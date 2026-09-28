# Database

SQLite in WAL mode, one file at `data/database/fb-automation.sqlite`.

The driver is `node:sqlite`, the SQLite built into Node, rather than a native
addon: a clean checkout then needs no compiler toolchain, which is also what
keeps Python out of the install. Drizzle builds the SQL through its proxy
driver and one serialised connection executes it — serialised because SQLite
itself is synchronous, and because a single queue is what makes `transaction()`
safe when several requests overlap.

Migrations are generated from the schema with drizzle-kit and applied at
startup.

## Tables

### `accounts`

| Column                     | Type                             | Notes                                                   |
| -------------------------- | -------------------------------- | ------------------------------------------------------- |
| `id`                       | text, PK                         | `acc_<time>_<random>`                                   |
| `name`                     | text, unique                     | Operator-facing identifier                              |
| `display_name`             | text                             | Shown in the UI                                         |
| `profile_id`               | text, FK → `browser_profiles.id` | One profile per account                                 |
| `status`                   | text                             | `offline` `starting` `online` `busy` `stopping` `error` |
| `enabled`                  | integer (0/1)                    | Disabled accounts are never scheduled                   |
| `last_error`               | text, null                       | Set when `status = 'error'`                             |
| `last_active_at`           | text, null                       | ISO-8601                                                |
| `created_at`, `updated_at` | text                             | ISO-8601                                                |

Indexes: unique on `name`, index on `status`, index on `enabled`.

### `browser_profiles`

| Column                     | Type                             | Notes                                            |
| -------------------------- | -------------------------------- | ------------------------------------------------ |
| `id`                       | text, PK                         | `prf_…`                                          |
| `account_id`               | text, unique, FK → `accounts.id` |                                                  |
| `slug`                     | text, unique                     | Directory name under the profile root            |
| `directory`                | text                             | Path **relative** to the configured profile root |
| `channel`                  | text                             | `chromium` `chrome` `msedge` `brave`             |
| `locked_by`                | text, null                       | Lock owner, `pid:sessionId`                      |
| `locked_at`                | text, null                       | Used with the TTL to detect a stale lock         |
| `last_used_at`             | text, null                       |                                                  |
| `created_at`, `updated_at` | text                             |                                                  |

Storing the directory relative to the root is what makes a traversal attempt
impossible to persist: an absolute or `..`-containing value is rejected before
the row is written.

### `jobs`

| Column                                                               | Type                                        | Notes                                                                    |
| -------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------ |
| `id`                                                                 | text, PK                                    | `job_…`                                                                  |
| `account_id`                                                         | text, FK → `accounts.id`, on delete cascade |                                                                          |
| `type`                                                               | text                                        | `create_post` `upload_media` `comment` `react_to_post` `send_message`    |
| `status`                                                             | text                                        | `pending` `queued` `running` `retrying` `completed` `failed` `cancelled` |
| `payload`                                                            | text (JSON)                                 | Validated against `AutomationActionSchema` on read and write             |
| `priority`                                                           | integer                                     | Higher first, default 0                                                  |
| `retry_count`                                                        | integer                                     |                                                                          |
| `max_retries`                                                        | integer                                     |                                                                          |
| `progress`                                                           | real                                        | 0–100                                                                    |
| `run_after`                                                          | text, null                                  | Scheduling and retry backoff                                             |
| `result`                                                             | text (JSON), null                           | `AutomationResultSchema`                                                 |
| `last_error`                                                         | text (JSON), null                           | `{ code, message, retryable, occurredAt }`                               |
| `created_at`, `queued_at`, `started_at`, `finished_at`, `updated_at` | text                                        |                                                                          |
| `locked_by`                                                          | text, null                                  | Worker that claimed the job                                              |

Indexes: `(status, priority DESC, created_at)` for claiming, `(account_id, status)`
for per-account concurrency, `(status, run_after)` for due work.

### `automation_logs`

| Column                                             | Type              | Notes                           |
| -------------------------------------------------- | ----------------- | ------------------------------- |
| `id`                                               | text, PK          |                                 |
| `level`                                            | text              | `debug` `info` `warn` `error`   |
| `message`                                          | text              |                                 |
| `event`                                            | text, null        | Dotted name, e.g. `job.started` |
| `account_id`, `job_id`, `session_id`, `request_id` | text, null        | Correlation                     |
| `context`                                          | text (JSON), null | Already redacted                |
| `created_at`                                       | text              |                                 |

Indexes: `created_at DESC`, `(level, created_at)`, `(account_id, created_at)`,
`(job_id, created_at)`.

### `settings`

Single-row key/value table (`key` PK, `value` JSON text, `updated_at`). Read
through `SettingsRepository`, which merges stored values over
`DEFAULT_SETTINGS` so a missing key never breaks a running system.

### `job_events` (optional, kept)

Append-only audit of every job status change: `id`, `job_id`, `from_status`,
`to_status`, `message`, `created_at`. Cheap to write, and it answers "why did
this job end up failed" without reconstructing it from logs.

## Rules

- Timestamps are ISO-8601 strings in UTC. SQLite has no date type and a text
  column sorts correctly, which is all the queue needs.
- JSON columns are parsed through the shared Zod schema. A row that cannot be
  parsed is an error, never a silently half-filled object.
- Raw SQL lives in `packages/database` only. HTTP controllers and use cases see
  repository interfaces.
- Claiming work happens inside a transaction (`claimDueJobs`), so two workers
  cannot take the same row.

## Migrations

```
pnpm db:generate   # drizzle-kit generate — writes SQL into packages/database/src/migrations
pnpm db:migrate    # applies every pending migration
```

The server also applies pending migrations at startup, so a fresh clone works
after `pnpm install && pnpm dev`.
