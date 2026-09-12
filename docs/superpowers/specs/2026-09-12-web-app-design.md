# Web App Design: one React UI for web, phone (iOS/Android) and desktop

**Date:** 2026-09-12
**Status:** approved in chat (architecture + four delivery decisions); this document is the written form for review.
**Supersedes:** the UI half of `2026-09-12-admin-shell-design.md`. The Tkinter admin-shell tasks (plan Tasks 4-12) are abandoned. The backend half of that spec (sheet `STATUS` mirror, `SheetWriter`, `DriverManager.login_accounts`, `profile_names=` on bulk commands) is kept and reused here.

## 1. Goal

The operator controls the Facebook automation from any device: a browser on any computer, an installed app icon on iPhone/Android (PWA), and an installed app window on Windows/Mac (browser "Install app"). One React frontend, one Python server, no native store apps.

## 2. Hard constraint

The bot itself cannot move. Playwright, the Brave profile directories, the SQLite database (`~/.autoshare/autoshare.db`), the Google service-account key and the queue worker all live on the Windows PC. Every other device is a remote control for that PC. The PC must be on and the server running for anything to work.

## 3. Decisions (made 2026-09-12)

| question | decision | rejected |
|---|---|---|
| Tk shell work | stop now; Tk app stays runnable as fallback, not extended | finish Tk first |
| access path | **VPS relay**: operator's own VPS terminates HTTPS and tunnels to the PC; PC connects outbound only | Tailscale (chosen first, then replaced when the operator said they already have a VPS); LAN-only |
| mobile | PWA (Add to Home Screen) | Capacitor/native store apps |
| desktop | browser / installed PWA | Tauri/Electron wrapper |
| where app code runs | **PC only**. VPS runs no application code, keeps no data | API hosted on the VPS + custom PC agent (two deployables, credentials at rest in the cloud, no benefit because DB and Brave are on the PC) |

## 4. Architecture

```
 phone / laptop browser
        │ https://<host>            (host = <vps-ip>.sslip.io or the operator's domain)
        ▼
 ┌─ VPS (Ubuntu) ─────────────────────────────┐
 │ Caddy :443  ── reverse_proxy 127.0.0.1:8000 │   TLS from Let's Encrypt, HSTS
 │ frps  :7000 ── tunnel server (token + TLS)  │   exposes 127.0.0.1:8000 on the VPS
 └─────────────────────────────────────────────┘
        ▲ outbound TCP from PC (no inbound port on the PC/router)
 ┌─ Windows PC ───────────────────────────────────────────────────┐
 │ frpc ──────── local 127.0.0.1:8000 → remote 8000 (loopback)     │
 │ server.py:  uvicorn(FastAPI) :8000 on 127.0.0.1                 │
 │   ├─ src/server/*  routes, auth, events bridge, static web/dist │
 │   ├─ DriverManager (unchanged) cmd_queue / result_queue         │
 │   ├─ SheetWatcher (unchanged) → drained by a server task        │
 │   └─ SQLite, config, state_cache, Brave profiles, Playwright    │
 └────────────────────────────────────────────────────────────────┘
```

- **VPS = infrastructure only.** Two binaries (Caddy, frp server) and two config files. No Python, no database, no copies of the sheet or passwords. If the VPS dies, a new one is a 10-minute runbook (section 11) and nothing is lost.
- **PC = the whole application.** `server.py` replaces `main.py` as the entry point for the web mode. `main.py` (Tk) is untouched and remains the fallback until the web UI has feature parity (end of phase 3).
- **Tunnel.** `frpc` on the PC keeps one authenticated, TLS-encrypted outbound connection to `frps` on the VPS. `frps` binds the tunnelled port on the VPS loopback only (`proxyBindAddr = "127.0.0.1"`), so the app is reachable on the VPS solely through Caddy. TLS terminates in Caddy; from Caddy to the PC the bytes travel inside the frp TLS tunnel. Plaintext exists only in Caddy's process memory on the VPS.
- **HTTPS is required**, not optional: iOS installs a PWA and registers a service worker only from a secure context.

## 5. Server package `src/server/`

| module | responsibility |
|---|---|
| `app.py` | `create_app(manager, watcher) -> FastAPI`: mounts routes, auth middleware, `/ws`, and serves `web/dist` (SPA fallback to `index.html`). |
| `auth.py` | Login with one operator account. Password hash (bcrypt) in `~/.autoshare/config.json` key `web_password_hash`, set by `python scripts/set_web_password.py`. Session = HMAC-signed token (`itsdangerous`) in an `HttpOnly; Secure; SameSite=Lax` cookie, 30-day expiry, rotated on login. Failed logins limited to 5 per 15 minutes per client IP (in memory). Every `/api/*` and `/ws` request without a valid session gets `401`; the SPA shows the login page. Origin header must match the configured public host on state-changing requests (CSRF guard). The server refuses to start in web mode until a password hash exists. |
| `events.py` | `EventBridge`: a thread that drains `manager.poll_result()` every 100 ms (same cadence as the Tk poll) and the watcher's `events` queue, applies side effects that `MainWindow._handle_result` and `_drain_sheet_events` used to apply (DB writes via `roster_sheet.apply`, `db.record_login_check`, run summaries, `SheetWriter` pushes), updates `state.py`, and broadcasts JSON events to every connected WebSocket. Log lines: `manager.log` is set to a function that appends to a ring buffer (last 2000 lines), writes the same daily log file `LogTab` wrote (`~/.autoshare/logs/`), and broadcasts `{"type":"log","stamp":...,"text":...,"level":"ok"|"error"|"info"}` using `LogTab.write`'s existing icon-to-level rule. |
| `state.py` | One `AppState` dataclass, the server-side replacement for what the Tk tabs held: `run` (kind, current, total, message, started_at, or null), `last_run_summary`, `pending_input` (the open `needs_input` prompt, or null), `login_run_active`, `sheet_last_ok`, `system` (RAM text from `manager.get_memory_stats()`, Brave process count). `GET /api/state` returns it plus the dashboard counts; a `{"type":"state", ...}` event is broadcast on every change. |
| `routes/accounts.py` | Accounts page and dashboard actions (section 7). |
| `routes/queue.py`, `routes/compose.py`, `routes/groups.py` | phase 2. |
| `routes/system.py` | `GET /api/state`, `GET /api/log?tail=N`, `POST /api/input` (answer to a `needs_input` prompt), `POST /api/stop` (`manager.stop_watch()` + `manager.cleanup()`), `GET /api/health` (unauthenticated, used by `frpc` health check). |
| `routes/settings.py` | phase 3 (delays, browser mode, batch size, password change). |

**Command path.** A route validates the JSON body with a Pydantic model, checks exclusivity (section 9), calls the existing `DriverManager` helper (`manager.login_accounts(usernames)`, `manager.check_login_status(profile_names)`, ...), records the run in `AppState`, and returns `202 {"accepted": true}`. Results never come back on the HTTP response; they arrive on `/ws`.

**Result path.** Worker result dicts already carry `"type": "<rtype>"` and JSON-serialisable fields. The bridge forwards each one verbatim as a WebSocket event after applying its side effect. The frontend reducer switches on the same `rtype` strings `MainWindow._handle_result` switches on today, so the parity proof (section 10) can compare the two lists.

**Prompts from the worker.** Today `auto_setup_images_preview` blocks the Tk thread in `ImagePickerDialog` and answers through `manager.send_user_response`. In web mode the bridge stores the prompt in `AppState.pending_input`, broadcasts `{"type":"needs_input","kind":"image_picker","profile_name":...,"images":[{"id":..,"url":"/api/images/<id>"}],"needs_pic":...}`, and the first device to `POST /api/input` answers it (`{"profile_pic": <id>|null, "cancel": bool}`); the server maps ids back to local paths and calls `manager.send_user_response`. Image bytes are served by `GET /api/images/<id>` from an allow-list built when the prompt was created, never from arbitrary paths. If nobody answers within 10 minutes the server sends `{"cancel": true}` so the worker never hangs.

**Sheet watcher.** `server.py` starts `SheetWatcher()` exactly as `app.run()` does; the bridge drains its queue and applies rows on the bridge thread (SQLite connection is `check_same_thread=False` already). `watcher.last_ok` feeds `AppState.sheet_last_ok`.

**Uploads (phase 2).** Compose images from a phone arrive as multipart, are stored under `~/.autoshare/uploads/<yyyy-mm-dd>/`, and are referenced by server-side path in queue items exactly as the desktop file picker did.

## 6. Frontend `web/`

Vite + React, seeded from the throwaway mockup in `mockup/react/` (which is deleted once `web/` exists). Built by `npm run build` into `web/dist`, which the server serves; `BUILD_WEB.bat` wraps it. `npm run dev` proxies `/api` and `/ws` to `127.0.0.1:8000` for development.

- **Shell:** left sidebar with the MCARSPH logo (the PNGs from `src/ui/assets/`, moved to `web/public/`), nav Dashboard / Accounts / Queue / Compose / Monitor / Log, brand red (`#d1202a` light, `#e2323c` dark) only on the logo and the active-nav bar, indigo accent and the light/dark palettes copied from `src/ui/theme.py`. Below 768 px the sidebar becomes a bottom tab bar. Page header shows the page title and, on Queue and Compose, the selection chip ("N selected").
- **Status bar** (bottom on desktop, folded into the header on phones): activity line, run progress, `Profiles · Active · Queue · RAM`.
- **Pages, phase 1:** Dashboard (four stat cards Total / Logged in / Pending / Disabled with count-up, "Log in pending accounts" button, Run / System / Alerts cards), Accounts (table with checkbox selection, filters, action bar: Log in selected, Check login, Auto-setup, Auto-setup all, Accept pending, Link/Unlink profile), Log (live tail, level colours, pause/scroll-lock). Login page.
- **Pages, phase 2:** Queue (build items, presets, run, watch URL, stop), Compose (share to groups / timeline / story, join groups, fetch groups, saved groups, bulk share, post to timeline with images).
- **Pages, phase 3:** Monitor (RAM/process stats, kill Brave processes), Settings (delays, browser mode, batch size, change password).
- **State:** one store. On load: `GET /api/state`, then open `/ws`. Every event is reduced into the store; the UI is a pure function of it. On WebSocket close: exponential backoff reconnect (1 s → 30 s), and on every reconnect a fresh `GET /api/state` so a phone that slept for an hour catches up without replaying events.
- **PWA:** `vite-plugin-pwa` generates the manifest (`display: standalone`, icons from the logo, theme colour per mode) and a service worker that precaches the app shell only. API responses are never cached. Offline shows a "PC unreachable" banner, nothing else.
- **Motion:** CSS transitions with the durations from `theme.MOTION` (page slide, sidebar collapse, press pulse, theme dip, count-up). Respect `prefers-reduced-motion`.

## 7. Phase 1 API

All routes need a session unless marked public. Bodies and responses are JSON.

| method + path | body → effect |
|---|---|
| `POST /api/login` (public) | `{password}` → sets cookie, `204`; `401` on mismatch; `429` when rate-limited |
| `POST /api/logout` | clears cookie |
| `GET /api/health` (public) | `{"ok": true, "version": "<git short sha or 'dev'>"}` |
| `GET /api/state` | `AppState` + `counts` `{total, logged_in, pending, disabled, profiles, active, queue}` (from `db.count_accounts`, `db.logged_in_profiles`, `db.count_pending`, `db.count_disabled`, `cfg.list_profiles`) |
| `GET /api/accounts` | rows = `db.list_accounts()` joined with `cfg.list_profiles()` and `db.logged_in_profiles()`: `{sheet_no, facebook_name, username, linked_profile, status, status_reason, sheet_status, logged_in, last_login_check}`; unlinked Brave profiles appear as rows with `username: null` so the Accounts page shows the same set `ProfilesTab` shows |
| `POST /api/accounts/login` | `{usernames: [..]}` → `manager.login_accounts(usernames)`; `409` if a login run is active |
| `POST /api/accounts/login-pending` | no body → `manager.login_accounts([a["username"] for a in db.pending_accounts()])`; `409` if a login run is active, `400` if none pending |
| `POST /api/accounts/check-login` | `{profile_names: [..] or null}` → `manager.check_login_status(profile_names)` |
| `POST /api/accounts/auto-setup` | `{profile_name, target_friends, pinterest_query, bio}` → `manager.auto_setup_profile(...)` |
| `POST /api/accounts/auto-setup-all` | `{target_friends, pinterest_query, bio, connect_friends, profile_names}` → `manager.auto_setup_all_profiles(...)` |
| `POST /api/accounts/accept-pending` | `{profile_names}` → `manager.accept_all_pending_requests(profile_names)` |
| `POST /api/accounts/link` | `{username, profile_name}` → `db.link_account`; `DELETE /api/accounts/link/{username}` unlinks |
| `POST /api/profiles/launch` | `{profile_name}` → `manager.start_profile(profile_name)` (opens a visible Brave window on the PC; the page says so) |
| `GET /api/log?tail=500` | last N ring-buffer lines |
| `POST /api/input` | answer to `AppState.pending_input`; `409` if none open |
| `POST /api/stop` | `manager.stop_watch()`; `manager.cleanup()` |
| `WS /ws` | server → client only: every worker result verbatim, `log`, `state`, `needs_input` |

## 8. Entry points and runbook files

- `server.py` (repo root): parses `--host 127.0.0.1 --port 8000 --dev`; builds `DriverManager()`, `create_app`, starts the manager thread, the watcher, the bridge, then `uvicorn.run`. On shutdown: `manager.stop()`, watcher stop, bridge stop. `--dev` allows `http://localhost` origins for `npm run dev`.
- `SERVER.bat`: starts `frpc` (if `tools/frp/frpc.toml` exists) and `python server.py` in two windows. `BUILD_WEB.bat`: `cd web && npm ci && npm run build`. `INSTALL.bat` gains the new Python packages and a Node check.
- `scripts/set_web_password.py`: prompts twice, stores the bcrypt hash.
- `tools/frp/frpc.toml` (gitignored; `frpc.example.toml` committed): `serverAddr`, `serverPort = 7000`, `auth.token`, `transport.tls.enable = true`, one proxy `type = "tcp"`, `localIP = "127.0.0.1"`, `localPort = 8000`, `remotePort = 8000`.
- `docs/runbooks/vps.md`: the VPS runbook (section 11).
- `requirements.txt` adds `fastapi`, `uvicorn[standard]`, `python-multipart`, `itsdangerous`, `bcrypt`.

## 9. Exclusivity and errors

- The worker is one thread; commands already queue behind each other. The server adds one rule: a command whose Tk button used to be disabled while a run was active returns `409 {"error": "... is running"}` instead of queueing, using the same flags `MainWindow` toggled (`login_run_active`, `run` not null). Everything else queues, as before.
- A route never blocks on the worker. Timeouts do not exist at the HTTP layer; progress and completion arrive on `/ws`.
- Worker exceptions are already caught and logged by `DriverManager._run`; the bridge additionally broadcasts `{"type":"error","text":...}` when a `*_result` carries `ok: false` with an `error` field, which the frontend shows as a toast and the Dashboard keeps in the Alerts card (last 20).
- If `manager.poll_result()` raises, the bridge logs and continues; the bridge thread never dies silently (a died bridge sets `AppState.bridge_alive = false`, shown as a red banner).

## 10. Proof

`verify.py` keeps running `proofs/*.py`. New proof files:

- `proofs/20_server.py`: `create_app(DriverManager(), watcher=None)` under FastAPI `TestClient` with the manager thread not started. Asserts: `/api/health` public; every `/api/*` route `401` without a cookie; login with a temporary hash sets the cookie; every phase-1 route with a valid body returns `202`/`200` and the expected dict lands on `manager.cmd_queue` (assert the `type` field); `/ws` accepts a connection and receives a `state` event first; a fake `login_accounts_progress` put on `manager.result_queue` reaches the WebSocket within 1 s; `needs_input` round trip; rate limiting after 5 bad logins.
- `proofs/21_parity.py`: the set of `rtype` strings in `MainWindow._handle_result` (parsed from source) minus the set handled by `src/server/events.py` (a module-level tuple `HANDLED_RTYPES`) must be empty; and every `manager.<helper>` that a Tk `set_on_*` callback reaches must appear in the routes' `USES` tuple. Both lists are explicit so the diff is readable.
- `proofs/22_web_build.py`: skipped with a printed notice when `node` is absent; otherwise `npm run build` in `web/` must exit 0 and `web/dist/index.html` must exist.

Proofs never open a browser, never contact Google, never touch the real Brave directory.

## 11. VPS runbook (summary; full text in `docs/runbooks/vps.md`)

Any Ubuntu 22.04/24.04 VPS with a public IP and ports 80, 443, 7000 open.

1. `apt install caddy`; `/etc/caddy/Caddyfile`:
   ```
   <host> {
       encode zstd gzip
       header Strict-Transport-Security "max-age=31536000"
       reverse_proxy 127.0.0.1:8000
   }
   ```
   where `<host>` is the operator's domain or `<vps-ip>.sslip.io`. Caddy obtains and renews the certificate itself.
2. Download the frp release, install `frps` as a systemd service with `/etc/frp/frps.toml`: `bindPort = 7000`, `auth.token = "<random 32 bytes>"`, `transport.tls.force = true`, `proxyBindAddr = "127.0.0.1"`.
3. `ufw allow 80,443,7000/tcp`; `ufw enable`.
4. On the PC: unzip the frp Windows release into `tools/frp/`, copy `frpc.example.toml` to `frpc.toml`, fill in `serverAddr` and the token, run `SERVER.bat`. Open `https://<host>` on the phone, log in, Share → Add to Home Screen.

The runbook is executed by the operator or by this assistant over SSH once the operator provides the VPS address and SSH access. No credentials are ever written into the repo.

## 12. Phasing

Each phase gets its own implementation plan under `docs/superpowers/plans/`.

1. **Core + Dashboard + Accounts + Log** (this spec's sections 5, 7, 8, 10, 11): server package, auth, bridge, state, phase-1 routes, PWA shell, three pages, login page, `SERVER.bat`, runbook. Done = operator logs in from an iPhone over the VPS host, sees live counts, presses "Log in pending accounts", watches progress, and the sheet `STATUS` cells update.
2. **Queue + Compose parity**: `routes/queue.py`, `routes/compose.py`, `routes/groups.py`, uploads, the two pages, selection model, presets.
3. **Monitor + Settings + retirement**: `routes/settings.py`, Monitor page, password change, Task Scheduler auto-start for `frpc` and `server.py`, then delete `src/ui/` Tk code and `main.py`, update README and memory.

## 13. Out of scope

Native store apps, push notifications, multi-user accounts and roles, running the bot anywhere but the operator's PC, and any change to `DriverManager`'s command or result contract.
