# FB Automation

A TypeScript automation system for driving Facebook accounts through persistent
Playwright browser profiles, with a React control panel, a persistent job queue
and live status over WebSocket.

No Python. No shell glue. One pnpm workspace.

## Stack

| Area       | Choice                                                                 |
| ---------- | ---------------------------------------------------------------------- |
| Frontend   | React 18, TypeScript, Vite, React Router, TanStack Query, Zustand, Zod |
| Backend    | Node 20+, TypeScript, Fastify 5, REST + WebSocket                      |
| Automation | Playwright, persistent Chromium/Brave profiles                         |
| Database   | SQLite, Drizzle ORM                                                    |
| Testing    | Vitest, Playwright Test                                                |
| Workspace  | pnpm monorepo                                                          |

## Requirements

- Node.js >= 20.11
- pnpm 9 (`npm install -g pnpm@9`)

## Getting started

```bash
pnpm install
cp .env.example .env
pnpm build          # packages must be built once before the apps resolve them
pnpm dev            # API on :3001, web on :5173
```

Open http://localhost:5173.

## Commands

| Command                 | Does                                                                |
| ----------------------- | ------------------------------------------------------------------- |
| `pnpm dev`              | Watch-build the packages, then run the API and the web app together |
| `pnpm dev:server`       | API only                                                            |
| `pnpm dev:web`          | Web app only                                                        |
| `pnpm build`            | Build every package and app in dependency order                     |
| `pnpm typecheck`        | `tsc --noEmit` everywhere                                           |
| `pnpm lint`             | ESLint, including the layer-boundary rules                          |
| `pnpm format`           | Prettier                                                            |
| `pnpm test`             | Unit and integration tests                                          |
| `pnpm test:unit`        | Unit tests only                                                     |
| `pnpm test:integration` | Integration tests only                                              |
| `pnpm test:e2e`         | Playwright end-to-end tests                                         |
| `pnpm db:generate`      | Generate a migration from the Drizzle schema                        |
| `pnpm db:migrate`       | Apply pending migrations                                            |

## Layout

```
apps/
  web/          React single-page application
  server/       Fastify API, WebSocket, composition root
packages/
  shared/       Zod contracts, error codes, utilities (browser-safe)
  domain/       Entities, state machines, repository interfaces
  application/  Use cases and ports
  database/     Drizzle schema, migrations, repositories
  automation/   Playwright browser lifecycle and Facebook actions
  queue/        Persistent job queue, locking, retries, recovery
  observability/Logger, event bus, metrics
data/           SQLite file, browser profiles, uploads, exports, logs
architecture/   Design documents
tests/          Integration and end-to-end suites
```

Read [architecture/README.md](./architecture/README.md) before changing
anything structural. The short version: dependencies point inwards, the browser
only ever talks to the API, and nothing outside `packages/automation` knows that
Playwright exists.

## Configuration

Every setting is read once, in `apps/server/src/config/env.ts`, and validated
with Zod. An invalid value stops the process at startup. See `.env.example` for
the full list.

Paths in `.env` are resolved against the repository root, so relative values
work no matter where the process was started.

## Status

Built in phases. Completed so far:

- **Phase 1 — Foundation.** Workspace, TypeScript configuration, linting,
  shared contracts, domain model, application ports, Fastify server with a
  health endpoint, React application shell.
