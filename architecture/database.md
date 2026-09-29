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

| Column                     | Type                             | Notes                                                                                                                                  |
| -------------------------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                       | text, PK                         | `acc_<time>_<random>`                                                                                                                  |
| `name`                     | text, unique                     | Operator-facing identifier                                                                                                             |
| `display_name`             | text                             | Shown in the UI                                                                                                                        |
| `profile_id`               | text, FK → `browser_profiles.id` | One profile per account                                                                                                                |
| `status`                   | text                             | `offline` `starting` `online` `busy` `stopping` `error`                                                                                |
| `enabled`                  | integer (0/1)                    | Disabled accounts are never scheduled                                                                                                  |
| `sheet_no`                 | integer, null                    | Row number on the roster sheet                                                                                                         |
| `username`                 | text, null                       | Facebook sign-in identifier; the key a roster import matches on                                                                        |
| `password`                 | text, null                       | As the roster supplied it; typed by the login job, never returned                                                                      |
| `gmail`                    | text, null                       |                                                                                                                                        |
| `gmail_password`           | text, null                       | As supplied; never returned                                                                                                            |
| `phone`                    | text, null                       |                                                                                                                                        |
| `facebook_name`            | text, null                       | The name Facebook shows, as last read from the profile                                                                                 |
| `profile_url`              | text, null                       |                                                                                                                                        |
| `proxy_url`                | text, null                       | The account's proxy, credentials included; parsed at launch. Every request from its browser goes through it. Never returned by the API |
| `totp_secret`              | text, null                       | Base32 authenticator secret. The login job generates the current code from it to answer a two-factor prompt. Never returned by the API |
| `login_status`             | text                             | `unknown` `logged_in` `logged_out` `checkpoint` `two_factor` `email_confirmation` `captcha` `disabled` `restricted`                    |
| `login_reason`             | text, null                       | The verdict in words                                                                                                                   |
| `last_login_check_at`      | text, null                       | ISO-8601                                                                                                                               |
| `share_restricted_until`   | text, null                       | Share jobs are refused until this passes; set for twelve hours when Facebook refuses a share by naming the account                     |
| `last_error`               | text, null                       | Set when `status = 'error'`                                                                                                            |
| `last_active_at`           | text, null                       | ISO-8601                                                                                                                               |
| `created_at`, `updated_at` | text                             | ISO-8601                                                                                                                               |

Indexes: unique on `name`, index on `status`, `enabled`, `username` and
`login_status`.

The roster columns are named after the sheet's headers so an import maps
header to column by name. Passwords are stored exactly as supplied: the login
job types them into Facebook, and there is no way to do that from a hash. They
leave the database through one door only, the credentials lookup the login
action uses. `toAccount` in `repositories/mappers.ts` turns them into the
`hasPassword` and `hasGmailPassword` booleans the API returns, so no view, export
or log line ever carries one. Treat the database file as a credential.

`login_status` is separate from `status` on purpose. `status` describes the
browser process; `login_status` describes what the last login or login check
found, and an account can be `online` and `logged_out` at the same time.

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

### `groups`

The groups an account belongs to, as last read off Facebook by a
`fetch_groups` job.

| Column       | Type                                        | Notes                                     |
| ------------ | ------------------------------------------- | ----------------------------------------- |
| `id`         | text, PK                                    | `grp_…`                                   |
| `account_id` | text, FK → `accounts.id`, on delete cascade |                                           |
| `name`       | text                                        |                                           |
| `url`        | text                                        | `https://www.facebook.com/groups/<slug>/` |
| `fetched_at` | text                                        | ISO-8601                                  |

Indexes: unique on `(account_id, url)`, index on `url`.

A fetch replaces the account's whole list, delete-then-insert inside one
transaction, so a fetch that finds nothing empties the list rather than leaving
yesterday's groups looking current. The unique index on `url` per account is
also what lets `/groups/summary` fold the same group seen through several
accounts into one row.

### `account_activity`

What each account has already done to a target: one share per group, one join
per group. A bulk run reads this to skip what is done.

| Column        | Type                                        | Notes                                                                        |
| ------------- | ------------------------------------------- | ---------------------------------------------------------------------------- |
| `id`          | text, PK                                    | `act_…`                                                                      |
| `account_id`  | text, FK → `accounts.id`, on delete cascade |                                                                              |
| `kind`        | text                                        | `share` `join`                                                               |
| `target_url`  | text                                        | For a share, `<postUrl>::<groupUrl or groupName>`; for a join, the group URL |
| `target_name` | text, null                                  | The group as Facebook named it                                               |
| `status`      | text                                        | `done` `pending` `failed`; a join request awaiting approval is `pending`     |
| `message`     | text, null                                  |                                                                              |
| `job_id`      | text, null                                  | The job that wrote the row                                                   |
| `created_at`  | text                                        | ISO-8601                                                                     |

Indexes: unique on `(account_id, kind, target_url)`, index on
`(account_id, created_at)`.

Recording the same target again updates the existing row rather than adding a
second, so the unique index holds and `doneTargets(accountId, kind)` — the
query behind `skipDone` on the fan-out endpoints — is a single indexed read of
the rows whose `status` is `done`.

### `jobs`

| Column                                                               | Type                                        | Notes                                                                    |
| -------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------ |
| `id`                                                                 | text, PK                                    | `job_…`                                                                  |
| `account_id`                                                         | text, FK → `accounts.id`, on delete cascade |                                                                          |
| `type`                                                               | text                                        | One of `JOB_TYPES` in `@fb/shared`; see the job types in `api.md`        |
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

There are two migrations so far. `0000_initial.sql` creates the original
tables; `0001_roster_groups_activity.sql` adds the roster and login-state
columns to `accounts`, their two indexes, and the `groups` and
`account_activity` tables.
