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

| Method | Path                          | Body                   | Returns                                           |
| ------ | ----------------------------- | ---------------------- | ------------------------------------------------- |
| GET    | `/accounts`                   | —                      | `Paginated<Account>`; `?search=&status=&enabled=` |
| POST   | `/accounts`                   | `CreateAccountSchema`  | `Account` (201)                                   |
| GET    | `/accounts/:id`               | —                      | `Account`                                         |
| PATCH  | `/accounts/:id`               | `UpdateAccountSchema`  | `Account`                                         |
| DELETE | `/accounts/:id`               | —                      | 204                                               |
| POST   | `/accounts/:id/enable`        | —                      | `Account`                                         |
| POST   | `/accounts/:id/disable`       | —                      | `Account`                                         |
| POST   | `/accounts/:id/browser/start` | `StartBrowserSchema`   | `BrowserSessionView` (202)                        |
| POST   | `/accounts/:id/browser/stop`  | —                      | 204                                               |
| GET    | `/accounts/:id/browser`       | —                      | `BrowserSessionView` or 404                       |
| GET    | `/browser/sessions`           | —                      | `{ sessions: BrowserSessionView[] }`              |
| POST   | `/accounts/import`            | `ImportAccountsSchema` | `ImportAccountsResult`                            |
| GET    | `/accounts/export`            | —                      | JSON file download                                |

Errors: `ACCOUNT_NOT_FOUND` 404, `ACCOUNT_NAME_TAKEN` 409,
`BROWSER_ALREADY_RUNNING` 409, `PROFILE_LOCKED` 409, `BROWSER_LAUNCH_FAILED` 500.

## Jobs

| Method | Path               | Body                   | Returns                                       |
| ------ | ------------------ | ---------------------- | --------------------------------------------- |
| GET    | `/jobs`            | —                      | `Paginated<Job>`; `?status=&accountId=&type=` |
| POST   | `/jobs`            | `CreateJobSchema`      | `Job` (201)                                   |
| POST   | `/jobs/batch`      | `CreateJobBatchSchema` | `Job[]` (201)                                 |
| GET    | `/jobs/:id`        | —                      | `Job`                                         |
| POST   | `/jobs/:id/cancel` | —                      | `Job`                                         |
| POST   | `/jobs/:id/retry`  | —                      | `Job`                                         |
| GET    | `/jobs/stats`      | —                      | `QueueStats`                                  |

Errors: `JOB_NOT_FOUND` 404, `JOB_NOT_CANCELLABLE` 409, `JOB_NOT_RETRYABLE` 409,
`ACCOUNT_DISABLED` 409.

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

Client messages: `{ "type": "ping" }` and
`{ "type": "subscribe", "payload": { "topics": [...] } }`.

Both directions are parsed with `ServerEventSchema` / `ClientMessageSchema`, so
a malformed frame is dropped and logged rather than reaching a React reducer.

The socket is a notification channel, not a data source: a client that receives
`job.completed` updates its TanStack Query cache, and anything it has not seen
is still available from the REST endpoints after a reconnect.
