# Dependency rules

## The direction

```
apps/web  ─────────────▶ @fb/shared
   │ (HTTP + WebSocket only)
   ▼
apps/server ───────────▶ @fb/application ──▶ @fb/domain ──▶ @fb/shared
   │                            ▲
   │                            │ implements ports and domain interfaces
   └──▶ @fb/database, @fb/automation, @fb/queue, @fb/observability
```

Arrows point at what a package is allowed to import. Nothing points back.

## Per-package rules

| Package             | May import                                    | Must never import                                                                  |
| ------------------- | --------------------------------------------- | ---------------------------------------------------------------------------------- |
| `@fb/shared`        | nothing in the workspace; `zod` only          | Node built-ins, any other `@fb/*`                                                  |
| `@fb/domain`        | `@fb/shared`                                  | Fastify, Drizzle, Playwright, React, any outer `@fb/*`                             |
| `@fb/application`   | `@fb/domain`, `@fb/shared`                    | Fastify, Drizzle, Playwright, React, `@fb/database`, `@fb/automation`, `@fb/queue` |
| `@fb/database`      | `@fb/domain`, `@fb/shared`, Drizzle           | Fastify, Playwright, React                                                         |
| `@fb/automation`    | `@fb/domain`, `@fb/shared`, Playwright        | Fastify, Drizzle, React                                                            |
| `@fb/queue`         | `@fb/application`, `@fb/domain`, `@fb/shared` | Playwright, Drizzle, Fastify, React                                                |
| `@fb/observability` | `@fb/application`, `@fb/shared`, pino         | Fastify, Drizzle, Playwright, React                                                |
| `apps/server`       | everything above                              | React                                                                              |
| `apps/web`          | `@fb/shared`                                  | every other `@fb/*`, every Node built-in, Playwright, Drizzle, Fastify             |

`@fb/shared` deliberately stays free of Node built-ins: `apps/web` bundles it
for the browser, so a single `node:fs` import there would break the build.

## Why the frontend is cut off

`apps/web` runs in somebody's browser. If it could import `@fb/database` it
could hold a database handle; if it could import `@fb/automation` it could hold
a browser process. Both would move trust to the wrong side of the network. The
browser therefore gets exactly two things: the shared contract, and the API.

## How the rules are enforced

1. **ESLint.** `eslint.config.js` declares a `no-restricted-imports` boundary
   per layer. A forbidden import fails `pnpm lint`, which fails CI.
2. **Package manifests.** A package cannot import what is not in its
   `dependencies`; pnpm's strict node_modules layout makes that a hard error
   rather than a lucky hoist.
3. **Ports.** The application layer names what it needs (`Repositories`,
   `FileStore`, `EventPublisher`, …) and the composition root in
   `apps/server/src/bootstrap/container.ts` is the only place that decides which
   concrete class satisfies each one.

## Practical consequences

- Adding a database column does not touch `@fb/application`.
- Swapping Playwright for another driver changes `@fb/automation` only, because
  everything above it depends on `AutomationGateway`.
- A use case can be unit-tested with fake ports and no SQLite, no browser and no
  HTTP server.
