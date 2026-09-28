# Architecture

FB Automation is a modular monolith written entirely in TypeScript. One Node
process serves the HTTP API, the WebSocket stream and the automation queue; one
React single-page application talks to it over HTTP and WebSocket.

| Document                                     | Contents                                             |
| -------------------------------------------- | ---------------------------------------------------- |
| [system-design.md](./system-design.md)       | Layers, runtime topology, package responsibilities   |
| [dependency-rules.md](./dependency-rules.md) | What each layer may import, and how it is enforced   |
| [database.md](./database.md)                 | SQLite schema, migrations, repository contracts      |
| [automation.md](./automation.md)             | Browser lifecycle, profile locking, Facebook actions |
| [api.md](./api.md)                           | REST contract and WebSocket event contract           |

## Reading order

1. `system-design.md` — the shape of the system.
2. `dependency-rules.md` — the rule that keeps that shape.
3. Then whichever area you are working in.

## Quick facts

- Package manager: pnpm workspaces. Node >= 20.11.
- No Python anywhere in the build, the runtime or the tooling.
- Database: SQLite via Drizzle ORM. One file under `data/database/`.
- Automation: Playwright driving persistent Chromium or Brave profiles.
- Transport: REST under `/api/v1`, live updates over a single WebSocket at `/ws`.
