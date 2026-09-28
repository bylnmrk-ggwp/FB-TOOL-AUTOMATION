# API contract

Base path `/api/v1`. Request and response bodies are JSON and are described by
Zod schemas in `@fb/shared`, which both the server and the browser import — the
contract is code, and this document describes it.

## Conventions

- `200` for a read, `201` for a create, `204` for a delete, `202` when work was
  accepted but not finished.
- Every error body is `{ "error": { "code", "message", "details"? } }`, where
  `code` is one of `ERROR_CODES` in `@fb/shared`.
- `x-request-id` is echoed on every response and appears in every server log
  line for that request.
- Lists are `{ items, total, limit, offset }` and accept `?limit=&offset=`.

## Accounts

| Method | Path                          | Body                                    | Returns                                                        |
| ------ | ----------------------------- | --------------------------------------- | -------------------------------------------------------------- |
| GET    | `/accounts`                   | —                                       | `Paginated<Account>`; `?search=&status=&loginStatus=&enabled=` |
| POST   | `/accounts`                   | `CreateAccountSchema`                   | `Account` (201)                                                |
| GET    | `/accounts/:id`               | —                                       | `Account`                                                      |
| PATCH  | `/accounts/:id`               | `UpdateAccountSchema`                   | `Account`                                                      |
| DELETE | `/accounts/:id`               | —                                       | 204                                                            |
| POST   | `/accounts/:id/enable`        | —                                       | `Account`                                                      |
| POST   | `/accounts/:id/disable`       | —                                       | `Account`                                                      |
| POST   | `/accounts/:id/browser/start` | `StartBrowserSchema`                    | `BrowserSessionView` (202)                                     |
| POST   | `/accounts/:id/browser/stop`  | —                                       | 204                                                            |
| GET    | `/accounts/:id/browser`       | —                                       | `BrowserSessionView` or 404                                    |
| GET    | `/browser/sessions`           | —                                       | `{ sessions: BrowserSessionView[] }`                           |
| POST   | `/accounts/import`            | `ImportAccountsSchema`                  | `ImportAccountsResult`                                         |
| POST   | `/accounts/import/sheet`      | —                                       | `ImportAccountsResult` plus `rows`                             |
| POST   | `/accounts/import/csv`        | `{ csv }`                               | `ImportAccountsResult` plus `rows`                             |
| GET    | `/accounts/export`            | —                                       | JSON file download                                             |
| POST   | `/accounts/login`             | `AccountIdsSchema` + `waitForOperator?` | `{ jobs: Job[] }` (202)                                        |
| POST   | `/accounts/check-login`       | `AccountIdsSchema`                      | `{ jobs: Job[] }` (202)                                        |
| GET    | `/accounts/:id/session`       | —                                       | `SessionExport`, as a file download                            |
| POST   | `/accounts/:id/session`       | `StorageStateSchema`, or `{ state }`    | 204                                                            |

Errors: `ACCOUNT_NOT_FOUND` 404, `ACCOUNT_NAME_TAKEN` 409,
`BROWSER_ALREADY_RUNNING` 409, `PROFILE_LOCKED` 409, `PROFILE_NOT_FOUND` 404,
`BROWSER_LAUNCH_FAILED` 500, `WORKBOOK_INVALID` 400.

### Roster fields and credentials

`Account` carries the roster fields (`sheetNo`, `username`, `gmail`, `phone`,
`facebookName`, `profileUrl`) and the login state (`loginStatus`,
`loginReason`, `lastLoginCheckAt`, `shareRestrictedUntil`). It never carries a
password: the view has `hasPassword` and `hasGmailPassword` booleans and nothing
else, and the JSON export is built from the same view. Create and PATCH accept
`password` and `gmailPassword` through `AccountCredentialsSchema`; an empty
string leaves the stored value alone and `null` clears it.

`loginStatus` is one of `LOGIN_STATUSES`: `unknown`, `logged_in`, `logged_out`,
`checkpoint`, `two_factor`, `email_confirmation`, `captcha`, `disabled`,
`restricted`. It is separate from `status`, which describes the browser: an
account can have a browser open and still be signed out.

### Importing the roster

`/accounts/import/sheet` reads the Google Sheet named in the environment and
`/accounts/import/csv` reads the text in the `csv` field (up to 2,000,000
characters, with quoted cells handled). Both hand their rows to
`RosterService`, which matches columns by header label (`FACEBOOK NAME`,
`USERNAME`, `PASSWORD`, `GMAIL`, `PASS FOR GMAIL`, `NUMBER`, `NO`, with a few
synonyms) and keys every row on its username. A known username updates the
roster fields and leaves status, profile and login verdict alone; a new one
creates an account; a row with no username is skipped. The result is the usual
`created` / `updated` / `skipped` counts plus `rows`, the number of roster rows
read. A missing key file, a service account Google refuses or a response of the
wrong shape all come back as `WORKBOOK_INVALID`.

### Login, login checks and sessions

`/accounts/login` and `/accounts/check-login` do not sign anybody in
themselves; they queue one `login` or `check_login` job per account at
priority 10 and answer 202 with the jobs. `waitForOperator` (default `true`)
decides what a login job does when Facebook puts a captcha, a code prompt or a
checkpoint in the way: wait for a person through the operator-input endpoints
below, or record the gate as the account's login status and finish.

The session endpoints move a signed-in session between machines as Playwright
storage state. Both work on the profile directory, so both are refused with
`BROWSER_ALREADY_RUNNING` while that account's browser is open. An imported
session sets `loginStatus` back to `unknown` until a login check has looked at
it, and a body that is not storage state is rejected as `WORKBOOK_INVALID`.

## Jobs

| Method | Path                    | Body                                                                                              | Returns                                       |
| ------ | ----------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| GET    | `/jobs`                 | —                                                                                                 | `Paginated<Job>`; `?status=&accountId=&type=` |
| POST   | `/jobs`                 | `CreateJobSchema`                                                                                 | `Job` (201)                                   |
| POST   | `/jobs/batch`           | `CreateJobBatchSchema`                                                                            | `{ jobs: Job[] }` (201)                       |
| POST   | `/jobs/share-to-groups` | `{ accountIds, postUrl, groups[], comments?, reaction?, shareToTimeline?, skipDone?, priority? }` | `{ jobs: Job[] }` (201)                       |
| POST   | `/jobs/join-groups`     | `{ accountIds, groupUrls, skipDone?, priority? }`                                                 | `{ jobs: Job[] }` (201)                       |
| POST   | `/jobs/cancel-all`      | —                                                                                                 | `{ cancelled: number }`                       |
| GET    | `/jobs/:id`             | —                                                                                                 | `Job`                                         |
| POST   | `/jobs/:id/cancel`      | —                                                                                                 | `Job`                                         |
| POST   | `/jobs/:id/retry`       | —                                                                                                 | `Job`                                         |
| GET    | `/jobs/stats`           | —                                                                                                 | `QueueStats`                                  |

Errors: `JOB_NOT_FOUND` 404, `JOB_NOT_CANCELLABLE` 409, `JOB_NOT_RETRYABLE` 409,
`ACCOUNT_DISABLED` 409.

### Job types

A job's `payload` is one member of `AutomationActionSchema`, discriminated on
`type`. The types are `create_post`, `upload_media`, `comment`, `react_to_post`,
`send_message`, `share_post` (to the account's own `timeline`, `story` or
`feed`), `share_to_group`, `join_group`, `fetch_groups`, `login`, `check_login`,
`accept_friend_requests`, `add_friends`, `auto_setup_profile` and `watch_live`.
Every payload's fields and defaults live in
`packages/shared/src/schemas/automation.ts`. Where a payload takes `comments`,
it is a pool of up to fifty lines and one is chosen at random per run, so a
batch across many accounts does not leave the same sentence under a post forty
times.

### Fan-out endpoints

`/jobs/share-to-groups` takes one post, a list of groups (`name`, optional
`url`) and a list of accounts, and creates one `share_to_group` job per account
and group, in the order given. With `skipDone` (default `true`) the groups an
account has already shared that post to, according to `account_activity`, are
left out. `shareToTimeline` rides on the first group job of each account only,
so a run over forty groups shares to the account's own timeline and story once,
not forty times. `/jobs/join-groups` does the same for `join_group` jobs, one
per account and group URL, again skipping what `account_activity` says is
done. Every account in the list is checked before anything is written, so a
batch that names a disabled or unknown account is rejected whole.

`/jobs/cancel-all` is the Stop button: running jobs are aborted through the
queue and everything still waiting is cancelled in one write.

## Groups and operator input

| Method | Path              | Body                          | Returns                                   |
| ------ | ----------------- | ----------------------------- | ----------------------------------------- |
| GET    | `/groups`         | —                             | `Paginated<Group>`; `?accountId=&search=` |
| GET    | `/groups/summary` | —                             | `{ groups: GroupSummary[] }`              |
| POST   | `/groups/fetch`   | `AccountIdsSchema`            | `{ jobs: Job[] }` (202)                   |
| GET    | `/input`          | —                             | `{ requests: OperatorRequest[] }`         |
| POST   | `/input`          | `AnswerOperatorRequestSchema` | 204                                       |

Errors: `OPERATOR_REQUEST_NOT_FOUND` 404.

A `Group` is one account's membership as last read from Facebook (`accountId`,
`name`, `url`, `fetchedAt`). `/groups/summary` folds the same URL seen through
several accounts into one `GroupSummary` (`url`, `name`, `accountIds`), which is
what the Compose picker shows. Nothing here scrapes anything: `/groups/fetch`
queues a `fetch_groups` job per account at priority 5, and each list is
replaced when its job finishes, announced by a `groups.changed` event.

`/input` is the human-in-the-loop seam. A job that meets a captcha, a code
prompt or a checkpoint pauses and publishes an `OperatorRequest` (`id`, `jobId`,
`accountId`, `kind`, `message`, `expectsText`, `createdAt`, `expiresAt`), where
`kind` is one of `captcha`, `two_factor`, `checkpoint`, `confirm` or `text`.
`GET /input` lists what is waiting; `POST /input` answers one with
`{ requestId, value?, cancel? }`. `value` is only needed when `expectsText` is
true; otherwise an empty answer means "I did it in the browser window".
`cancel: true` fails the job instead. Requests live in memory only and expire
after `settings.operatorInputTimeoutMs` (180 seconds by default), at which point
the waiting job fails with `OPERATOR_INPUT_TIMEOUT`. The Monitor page in the
web app renders these prompts.

## Media

| Method | Path     | Body           | Returns    |
| ------ | -------- | -------------- | ---------- |
| POST   | `/media` | multipart file | `MediaRef` |

The response id is what a job payload references. A client never sends a
filesystem path, and the server never accepts one.

## Logs, settings, dashboard, health

| Method | Path              | Returns                                                                     |
| ------ | ----------------- | --------------------------------------------------------------------------- |
| GET    | `/logs`           | `Paginated<LogEntry>`; `?level=&accountId=&jobId=&event=&search=&from=&to=` |
| GET    | `/settings`       | `Settings`                                                                  |
| PATCH  | `/settings`       | `Settings` (body `UpdateSettingsSchema`)                                    |
| GET    | `/settings/paths` | `SystemPaths` (read-only, from the environment)                             |
| GET    | `/dashboard`      | `DashboardStats`                                                            |
| GET    | `/health`         | `Health`; 200 when `ok`, 503 when `degraded`                                |

`Settings` includes the anti-spam delay ranges (`betweenShares`,
`afterShareButton`, `afterPost`, `betweenJoins`, `afterComment`, each as a
`…MinMs` / `…MaxMs` pair, alongside the older `minActionDelayMs` /
`maxActionDelayMs`) and `operatorInputTimeoutMs`. A PATCH is validated against
the settings as they would be after the change, and a minimum that exceeds its
maximum is rejected with `SETTINGS_INVALID` 400.

`DashboardStats` carries `accounts.byLoginStatus` (a count for every
`LOGIN_STATUSES` value, for the roster donut), `jobs.hourly` (the last 24 hours
as one bucket per hour, oldest first, zero-filled, with `completed`, `failed`
and `cancelled` counts) and `jobs.byType` (finished jobs in the last 24 hours by
type, most first). It is assembled in one server-side read so every number
describes the same moment.

## WebSocket contract

One socket at `/ws`. The server pushes; the client sends almost nothing.

Every message has the same envelope:

```json
{ "type": "job.progress", "timestamp": "2026-01-01T12:00:00.000Z", "payload": {} }
```

| Event                                                                            | Payload                                                       |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `connection.ready`                                                               | `{ clientId, serverVersion }`                                 |
| `account.created` / `account.updated`                                            | `Account`                                                     |
| `account.deleted`                                                                | `{ accountId }`                                               |
| `account.status.changed`                                                         | `{ accountId, status, previousStatus, reason }`               |
| `browser.started`                                                                | `BrowserSessionView`                                          |
| `browser.stopped`                                                                | `{ accountId, sessionId, reason }`                            |
| `browser.error`                                                                  | `{ accountId, code, message }`                                |
| `job.created` / `job.started` / `job.completed` / `job.failed` / `job.cancelled` | `Job`                                                         |
| `job.progress`                                                                   | `{ jobId, accountId, progress, step }`                        |
| `job.retrying`                                                                   | `{ jobId, accountId, retryCount, maxRetries, nextAttemptAt }` |
| `queue.stats`                                                                    | `QueueStats`                                                  |
| `log.created`                                                                    | `LogEntry`                                                    |
| `groups.changed`                                                                 | `{ accountId, count }`                                        |
| `input.requested`                                                                | `OperatorRequest`                                             |
| `input.resolved`                                                                 | `{ requestId, jobId, cancelled }`                             |

Client messages: `{ "type": "ping" }` and
`{ "type": "subscribe", "payload": { "topics": [...] } }`.

Both directions are parsed with `ServerEventSchema` / `ClientMessageSchema`, so
a malformed frame is dropped and logged rather than reaching a React reducer.

The socket is a notification channel, not a data source: a client that receives
`job.completed` updates its TanStack Query cache, and anything it has not seen
is still available from the REST endpoints after a reconnect.
