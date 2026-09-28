# System design

## Runtime topology

```
┌──────────────────────┐        HTTP  /api/v1/*        ┌───────────────────────────────┐
│  apps/web (browser)  │ ────────────────────────────▶ │  apps/server (Node process)   │
│  React + Vite        │ ◀──────────────────────────── │  Fastify + WebSocket + queue  │
└──────────────────────┘        WebSocket  /ws         └───────────────┬───────────────┘
                                                                       │
                                            ┌──────────────────────────┼──────────────────────────┐
                                            ▼                          ▼                          ▼
                                   ┌────────────────┐        ┌──────────────────┐       ┌──────────────────┐
                                   │ SQLite (file)  │        │ Playwright       │       │ data/ directory  │
                                   │ Drizzle ORM    │        │ Chromium / Brave │       │ profiles, uploads│
                                   └────────────────┘        └──────────────────┘       └──────────────────┘
```

Everything the user sees is produced by the browser application. Everything that
touches a database, a browser process or the filesystem happens inside the
server process. There is no third deployable.

## Layers

| Layer               | Lives in                                                                               | Knows about                                     |
| ------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------- |
| Presentation (web)  | `apps/web`                                                                             | HTTP/WebSocket contract from `@fb/shared`       |
| Presentation (HTTP) | `apps/server/src/http`                                                                 | Use cases, request/response mapping             |
| Application         | `packages/application`                                                                 | Domain contracts and ports                      |
| Domain              | `packages/domain`                                                                      | Entities, state machines, repository interfaces |
| Infrastructure      | `packages/database`, `packages/automation`, `packages/queue`, `packages/observability` | Concrete technology                             |

A request travels inwards and a result travels back out:

```
React component
  └─ TanStack Query hook
      └─ api client (fetch, validates with a shared Zod schema)
          └─ Fastify route  →  controller
              └─ application use case
                  └─ domain interface (AccountRepository, AutomationGateway, …)
                      └─ infrastructure implementation (Drizzle, Playwright, filesystem)
```

## Package responsibilities

### `packages/shared`

The contract both sides agree on: Zod schemas, the types inferred from them,
error codes, structured error classes and small pure utilities. It imports
nothing from the workspace and nothing from Node, so the browser can use it.

### `packages/domain`

Entities and the rules that do not depend on any technology: the account status
machine, the job status machine, queue ordering, retry classification, and the
repository interfaces the application layer programs against. Depends on
`@fb/shared` only.

### `packages/application`

Use cases — one class per thing a user can ask the system to do — plus the ports
through which a use case reaches the outside world (`Logger`, `EventPublisher`,
`FileStore`, `ProfileStorage`, `QueuePort`, `Repositories`). Depends on
`@fb/domain` and `@fb/shared`. Never on Fastify, Drizzle or Playwright.

### `packages/database`

Drizzle schema, migrations, and the repository implementations that satisfy the
domain interfaces. This is the only package that speaks SQL.

### `packages/automation`

Playwright. Browser lifecycle (`BrowserManager`, `BrowserLauncher`,
`BrowserContextManager`), persistent profiles (`ProfileManager`,
`ProfileLockManager`), and the Facebook implementation of `AutomationGateway`,
split into navigation, session, per-action modules and centralised selectors.

### `packages/queue`

The persistent job queue: claiming due jobs, per-account locking, global
concurrency, retry backoff, cancellation and recovery after a restart. It talks
to `JobRepository` and `AutomationGateway`, never to Playwright directly.

### `packages/observability`

The pino-backed `Logger`, the in-process event bus and a small metrics
registry — the implementations of the observability ports.

### `apps/server`

Composition root. Reads and validates configuration, builds every concrete
implementation in one container, mounts the HTTP routes and the WebSocket
server, starts the queue, and shuts all of it down cleanly.

### `apps/web`

React application. Feature-first folders (`features/accounts`, `features/queue`,
…), TanStack Query for everything the server owns, Zustand for the handful of
things only the browser knows (theme, filters, panel state).

## Cross-cutting decisions

**Runtime state versus stored state.** A running browser is an object with a
process handle; it lives in `BrowserManager`'s in-memory registry and never in
SQLite. What SQLite stores is the account, its profile metadata, and the last
observed status.

**Jobs are rows first.** A job exists in the database before it exists in the
worker. A restart therefore loses nothing: recovery reads the rows back.

**One error vocabulary.** Every deliberate failure is an `AppError` subclass
carrying a stable code, an HTTP status and a retryable flag. The HTTP layer maps
it once; the queue reads the same flag to decide whether to retry.

**Validation at the edges.** Untrusted values are `unknown` until a Zod schema
from `@fb/shared` has parsed them — in the controller on the way in and in the
API client on the way back.
