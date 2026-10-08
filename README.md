# FB Automation

A TypeScript automation system for driving Facebook accounts through persistent
Playwright browser profiles, with a React control panel, a persistent job queue
and live status over WebSocket.

No Python. No shell glue. One pnpm workspace.

## Stack

| Area       | Choice                                                                                            |
| ---------- | ------------------------------------------------------------------------------------------------- |
| Frontend   | React 19, TypeScript, Vite, React Router, TanStack Query, Zustand, Zod, Tailwind CSS 4, shadcn/ui |
| Backend    | Node 22.5+, TypeScript, Fastify 5, REST + WebSocket                                               |
| Automation | Playwright, persistent Chromium/Brave profiles                                                    |
| Roster     | Google Sheets (link-shared, or through a service account), or a pasted CSV                        |
| Database   | SQLite, Drizzle ORM                                                                               |
| Testing    | Vitest, Playwright Test                                                                           |
| Workspace  | pnpm monorepo                                                                                     |

## Requirements

- Node.js >= 22.5 (`node:sqlite` is the database driver)
- pnpm 9 (`npm install -g pnpm@9`)

## Getting started

```bash
pnpm install
cp .env.example .env
pnpm exec playwright install chromium   # the browser the automation drives
pnpm build                              # packages are built before the apps resolve them
pnpm dev                                # API on :3001, web on :5173
```

Open http://localhost:5173.

## Commands

| Command                  | Does                                                                |
| ------------------------ | ------------------------------------------------------------------- |
| `pnpm dev`               | Watch-build the packages, then run the API and the web app together |
| `pnpm dev:server`        | API only                                                            |
| `pnpm dev:web`           | Web app only                                                        |
| `pnpm build`             | Build every package and app in dependency order                     |
| `pnpm typecheck`         | `tsc --noEmit` everywhere                                           |
| `pnpm lint`              | ESLint, including the layer-boundary rules                          |
| `pnpm format`            | Prettier                                                            |
| `pnpm test`              | Unit and integration tests                                          |
| `pnpm test:unit`         | Unit tests only                                                     |
| `pnpm test:integration`  | Integration tests only                                              |
| `pnpm test:e2e`          | Playwright end-to-end tests                                         |
| `pnpm service:install`   | Register the built system as a Windows service (see below)          |
| `pnpm service:uninstall` | Remove that service; data and profiles stay                         |
| `pnpm db:generate`       | Generate a migration from the Drizzle schema                        |
| `pnpm db:migrate`        | Apply pending migrations                                            |

## Running as a Windows service

`pnpm dev` stops when its terminal closes. For a machine that should keep
sharing overnight, register the built system as a service:

```bash
winget install --id NSSM.NSSM -e      # once: the service wrapper
pnpm build
pnpm service:install                  # asks for administrator rights
```

The service (`FBAutomation`) starts with Windows, restarts itself if it
crashes, and runs one process: the API, which also serves the built control
panel. Open http://localhost:3001 (or the `PORT` in `.env`). Logs are written
to `data/logs/service.out.log` and `service.err.log`. Re-run
`pnpm service:install` after every `pnpm build` to pick up changes;
`pnpm service:uninstall` removes it and leaves the database and profiles alone.

A service has no desktop, so nothing it opens can be seen. Keep **Run
headless** on in Settings while it runs. When an account needs a captcha or
checkpoint solved by hand, stop the service (`nssm stop FBAutomation`), run
`pnpm dev` with headless off for that session, then start the service again.

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

The roster Google Sheet is configured the same way. `SHEETS_SHEET_ID` names
the spreadsheet and `SHEETS_TAB` the tab to read (default `Sheet1`). A sheet
shared with "anyone with the link can view" needs nothing more: it is read as
CSV without credentials. A private sheet needs `SHEETS_SERVICE_ACCOUNT` to
point at a service-account JSON key the sheet has been shared with (default
`./.secrets/sheets-service-account.json`); when that file exists it is used
instead. The `.secrets/` directory is ignored by git, so the key never leaves
the machine it was placed on.

## How it fits together

- A job is written to SQLite before it runs. Accepting one is a database write,
  not a start signal, so a crash a moment later loses nothing.
- A browser is a process handle, so it lives in memory only. What SQLite keeps
  is the account, its profile, and the last observed status.
- One account runs one job at a time. The profile lock in the database stops a
  second process from opening the same profile; an in-memory lock stops two
  workers in this process from queueing behind each other.
- A job interrupted by a restart is not repeated automatically: it may already
  have posted. It is failed with an explanation and offered for a deliberate
  retry.
- What an account has already done is written down. Every finished group share
  and group join lands in `account_activity`, so a bulk run over the same
  groups tomorrow skips the ones that are already done instead of sharing there
  twice.
- A share that Facebook refuses by naming the account is treated as a
  restriction, not a hiccup. The account's share jobs are held for twelve hours;
  every other kind of job still runs.
- A job that meets a captcha, a two-factor prompt or a checkpoint does not fail
  straight away. It stops, the Monitor page shows the prompt, and the person
  who deals with it in the browser window confirms it there. If nobody answers
  within the configured wait (three minutes by default), the job fails.

## The roster

Accounts come from a roster rather than being typed in one at a time. The
Accounts page can pull the configured Google Sheet, or take a CSV pasted into
the import dialog; both go through the same `RosterService`. Columns are matched
by their header label, never by position, so the sheet can be reordered: the
labels it looks for are `FACEBOOK NAME`, `USERNAME`, `PASSWORD`, `GMAIL`,
`PASS FOR GMAIL`, `NUMBER` and `NO` (a blank first header is also taken as the
row number). Only rows with both a username and a password count — a row
that cannot sign in is a heading, a note or a slot not filled in yet. Column
A — the row number — is the key: a row already known updates its roster
fields, a new one creates an account with its own browser profile, and a
roster account whose row stops counting (or disappears) is removed, so the
account count here is the count of usable rows over there. Accounts added by
hand carry no row number and are never touched by an import.

Passwords are stored so that the login job can type them, but they never come
back out. The API reports `hasPassword` and `hasGmailPassword` and nothing more,
and the JSON export leaves them out. That makes the SQLite file itself a
credential; keep `data/` as private as the `.secrets/` directory.

## Signing in

There are two ways to get a profile signed in, and both leave the session in
the persistent profile for every job that follows.

The first is by hand: start a browser from the Accounts page and sign in inside
that window. This still works exactly as before and is the fallback for
anything the automation cannot get past.

The second is the login job. Select accounts on the Accounts page and queue a
login; it types the stored username and password with human timing and human
mouse movement, ticks the "I'm not a robot" box itself, and stops for a person
whenever Facebook asks for a captcha picture, a two-factor code or a checkpoint.
The prompt appears on the Monitor page and the browser window stays open, so
the usual answer is to finish the step in the window and press "Done". The
outcome, whichever way it went, is recorded on the account as its login status,
and a separate check-login job re-reads that status without typing anything.

A signed-in session can also be moved between machines. The Accounts page
exports it as a Playwright storage-state file and imports one back; either
direction is refused while that account's browser is running, and an imported
session counts as unknown until a login check has looked at it.

## Remote access

The API stays on `127.0.0.1`. To reach it from a phone, Tailscale Funnel
publishes it at `https://<pc>.<tailnet>.ts.net`, and a password protects it.

1. Set `AUTH_PASSWORD` and `AUTH_SECRET` in `.env` (see `.env.example`), and
   add the panel's origin to `CORS_ORIGIN`. Restart the server.
2. On the PC, once:

   ```
   winget install --id tailscale.tailscale -e
   tailscale up
   tailscale funnel --bg 3001
   ```

   `tailscale up` opens a browser login. The first `tailscale funnel` prints a
   link to enable Funnel for the tailnet; follow it, then run the command
   again. `tailscale funnel status` shows the public URL. The Funnel survives
   reboots.

3. Open the URL from step 2 on any device: the API serves the built panel at
   `/`, and the login page asks for `AUTH_PASSWORD`.

To serve the panel from Vercel as well, the project builds this repository's
`main` with `vercel.json`. In the Vercel project settings, leave Root
Directory empty and set the Production environment variable
`VITE_PUBLIC_API_URL` to the Funnel URL from step 2. The Vercel page then
talks to the API on the PC directly; the PC must be on and the server running.

Tokens last thirty days. Changing `AUTH_SECRET` signs every device out.
Five wrong passwords lock the login for fifteen minutes.

## Not ported from the old system

A few things the previous system did were left behind on purpose, and none of
them are hiding somewhere waiting to be switched on:

- The memory tracker.
- The Groq-based gender and friendship summary.
- Pinterest scraping for profile pictures. A profile picture is now a file
  uploaded through the media endpoint and referenced by id.
- Parsing `.xlsx` workbooks. The roster is read from the Google Sheet or from a
  pasted CSV instead.
- Writing status back to the sheet. The sheet is read-only to this system; the
  login status lives in the database and on the Accounts page.
