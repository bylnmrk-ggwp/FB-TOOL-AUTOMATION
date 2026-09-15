# AutoShare — Facebook Post Sharer

Desktop tool that shares Facebook posts to groups and timelines, adds reactions
and comments, and manages friend connections across several accounts. It drives
your existing Brave browser profiles through Playwright, so each account stays
logged in and you never re-enter credentials.

Python 3.12+, Windows. A Tkinter desktop window, plus a web app for a phone
or any browser that the same PC serves; see [Web app](#web-app).

## Install

```bat
INSTALL.bat
```

Installs everything in `requirements.txt`, downloads the Chromium runtime, and
confirms the app imports. To check without changing anything:

```bat
python scripts/diagnose_and_fix.py --check
```

### Optional: Groq API key

Gender detection and the friendship-network summary call Groq. Both fall back to
local logic when no key is present, so this is optional.

```bat
setx GROQ_API_KEY "your-key-here"
```

Open a new terminal afterwards. Get a key at https://console.groq.com/keys.
Never commit it — `.env` is gitignored; see `.env.example`.

## Run

```bat
RUN_APP.bat
```

`RUN_APP.bat` (`python main.py`) now opens the **web UI** — the sidebar admin
shell (Dashboard, Accounts, Queue, Compose, Monitor, Log) — in your browser.
On the first run it builds `web/dist` with npm and, if no web password is set
yet, prompts you for one; then it starts the server and opens
`http://127.0.0.1:8000`. Flags: `--port N`, `--no-open`, and `--tk` for the
old desktop window (the no-Node fallback):

```bat
python main.py            :: web UI in the browser
python main.py --tk       :: the old Tkinter window
```

The old Tk window has two tabs — **Workspace** (Profiles beside the share
Queue, Log docked below) and **Share Center** (composer over the Memory
Monitor). Both UIs drive the same DriverManager, database and Brave profiles.

## Web app

The same operations from a phone or any browser. `server.py` runs on this PC
next to the bot (FastAPI plus the React build in `web/dist`); every other
device is a remote control, so the PC must be on with `SERVER.bat` running.

One-time setup on the PC:

```bat
INSTALL.bat                          adds the server packages from requirements.txt
python scripts\set_web_password.py   the one operator password, asked twice (8+ chars)
BUILD_WEB.bat                        needs Node 24; builds web\dist
```

Then:

```bat
SERVER.bat
```

serves `http://127.0.0.1:8000` on this PC only. To reach it from a phone it is
published through your VPS (Caddy for HTTPS, an `frp` tunnel out of the PC, no
inbound port on the router): follow [docs/runbooks/vps.md](docs/runbooks/vps.md)
once, after which `SERVER.bat` also starts the tunnel whenever
`tools/frp/frpc.toml` exists. On the phone open `https://<host>`, log in, then
Share > Add to Home Screen (iPhone) or Install app (Android) for an app icon.

Phase 1 covers Dashboard, Accounts and Log. Queue, Compose and Monitor still
live in the desktop window, so `RUN_APP.bat` (`main.py`) remains the fallback
and runs unchanged. Do not run both at once: they would drive the same Brave
profiles.

Frontend development: `python server.py --dev` and `npm run dev` in `web/`,
which proxies `/api` and `/ws` to the server.

## CLI

`scripts/cli.py` covers the same operations without the GUI:

```bat
python scripts/cli.py share <post_url> <group_url>
python scripts/cli.py share-timeline <post_url>
python scripts/cli.py login <email> <password>
python scripts/cli.py batch <file.json>
```

`python scripts/cli.py --help` lists every subcommand.

## Anti-spam delays

Every delay between shares, comments and navigations is configurable and exists
to protect the accounts. Do not set them to zero.

```bat
CONFIGURE_DELAYS.bat
```

Full reference: [docs/delay-settings.md](docs/delay-settings.md).

## Account roster

The roster lives in the local SQLite database. It is filled from an `.xlsx`
workbook by `scripts/import_accounts.py`, and thereafter the database is the
source of truth. Columns are matched by **header label**, never by position,
so the workbook can be reordered:

| header | database column |
|---|---|
| *(blank)* or `NO` | `sheet_no` (falls back to the row number) |
| `FACEBOOK NAME` | `facebook_name` |
| `USERNAME` | `username` (the key; rows without one are skipped) |
| `PASSWORD` | `password` |
| `GMAIL` | `gmail` |
| `PASS FOR GMAIL` | `gmail_password` |
| `NUMBER` | `number` |

`linked_profile`, `status` and `status_reason` are owned by this machine and an
import never touches them. A blank `status` is the "pending" set the dashboard
counts; `record_login_check()` is the only thing that fills it.

The database stores the two password columns in plaintext at the operator's
request. Treat `~/.autoshare/autoshare.db` and its `.bak-*` copies as
credentials.

```bat
python scripts/import_accounts.py --xlsx FILE    import a workbook into the database
python scripts/import_accounts.py --xlsx FILE --dry-run
                                                 show what an import would do
python scripts/provision_profiles.py --dry-run   plan Brave profiles, then run without --dry-run
python scripts/login_accounts.py                 assisted login, one visible browser at a time
python scripts/login_accounts.py --unattended --batch 10 --pause 20
                                                 same, no prompts: skips any checkpoint, pauses between batches
python scripts/provision_profiles.py --rename-from-roster
python scripts/export_sessions.py --out transfer  export signed-in sessions for another PC
python scripts/import_sessions.py --in transfer   inject them into this PC's Brave profiles
python scripts/setup_machine.py --xlsx FILE       a fresh clone -> a working fleet, in one command
```

Accounts Facebook has disabled are marked during login and skipped afterwards;
`python scripts/provision_profiles.py --purge-disabled --dry-run` shows what
`--purge-disabled` would remove.

## Utility scripts

| Launcher | Script | Purpose |
|---|---|---|
| `BUILD_WEB.bat` | `web/` (`npm ci && npm run build`) | Build the React frontend into `web/dist` for `server.py` to serve |
| `CHECK_FRIENDSHIPS.bat` | `scripts/check_friendships.py` | Friendship status for every saved profile, from the local database |
| | `scripts/check_login_status.py` | Live login scan of all Brave profiles; detects the "See more on Facebook" dialog a URL check misses |
| `CONFIGURE_DELAYS.bat` | `scripts/configure_delays.py` | Edit the anti-spam delays |
| `INSTALL.bat` | `scripts/diagnose_and_fix.py` | Install or repair dependencies; `--check` only reports |
| `SERVER.bat` | `server.py` | Web app server on `127.0.0.1:8000`, plus the `frpc` tunnel when `tools/frp/frpc.toml` exists |
| | `scripts/set_web_password.py` | Set the web app password; `--check` reports whether one exists |
| | `scripts/setup_machine.py` | Import roster, provision profiles, inject sessions, check logins - in order |
| | `scripts/export_sessions.py` | Export each profile's Facebook session as portable JSON |
| | `scripts/import_sessions.py` | Inject exported sessions into this PC's Brave profiles |
| | `verify.py` | Proof harness: compiles every module, imports all of them, builds the window and asserts the callback wiring |

## Layout

```
main.py              desktop entry point (RUN_APP.bat)
server.py            web entry point (SERVER.bat): FastAPI over the same DriverManager
verify.py            proof harness; also runs every proofs/*.py
requirements.txt     the only dependency list; INSTALL.bat reads it
*.bat                double-click launchers; each one runs a script below
scripts/             operator tools: roster import, profile provisioning,
                     assisted login, status checks, delay config, CLI,
                     web password
proofs/              one file per proof, run by verify.py
docs/                delay-settings.md, runbooks/vps.md (publish the web app)
tools/frp/           frpc.example.toml; frpc.exe and frpc.toml live here, gitignored
src/app.py           builds DriverManager + MainWindow and wires the log
src/core/            DriverManager (one asyncio worker behind a command queue)
                     FacebookAutomation (Playwright driving)
                     memory_tracker
src/storage/         config_manager, SQLite database, storage_state cache,
                     roster_import (workbook rows -> accounts)
src/server/          FastAPI app: auth, routes, EventBridge (worker results -> WebSocket),
                     AppState, log ring; serves web/dist
src/ui/              two-tab window over five tab classes, theme, effects
web/                 Vite + React PWA; npm run build -> web/dist
```

All Facebook work is serialized through a single background thread: the UI puts
commands on `cmd_queue` and polls `poll_result()` every 100 ms. Chromium locks
the shared Brave user-data directory, so login extraction runs sequentially by
necessity.

## Verifying a change

There is no test suite. After any edit:

```bat
python verify.py
```

It must print `ALL PROOFS PASS`.
