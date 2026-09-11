# AutoShare — Facebook Post Sharer

Desktop tool that shares Facebook posts to groups and timelines, adds reactions
and comments, and manages friend connections across several accounts. It drives
your existing Brave browser profiles through Playwright, so each account stays
logged in and you never re-enter credentials.

Tkinter GUI, Python 3.12+, Windows.

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

Or `python main.py`. The window has two tabs:

- **Workspace** — Profiles (add Brave profiles, auto-setup, login status,
  friend requests) beside the share Queue, with the Log docked below.
- **Share Center** — the share composer over the Memory Monitor.

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

The roster lives in a Google Sheet (id in `src/storage/sheets_api.py`,
override with `SHEETS_SHEET_ID`). The app reads it through a service account
whose key sits at `.secrets/sheets-service-account.json` (gitignored; override
with `SHEETS_SERVICE_ACCOUNT`). Columns are matched by **header label**, never
by position, so the sheet can be reordered:

| header | database column |
|---|---|
| *(blank)* or `NO` | `sheet_no` (falls back to the row number) |
| `FACEBOOK NAME` | `facebook_name` |
| `USERNAME` | `username` (the key; rows without one are skipped) |
| `PASSWORD` | `password` |
| `GMAIL` | `gmail` |
| `PASS FOR GMAIL` | `gmail_password` |
| `NUMBER` | `number` |
| `STATUS` | written *to* the sheet from `status` / `status_reason`; never imported |

`linked_profile`, `status` and `status_reason` are owned by this machine and a
sync never touches them.

While the app runs it polls the sheet every 20 s and applies any change to the
local database; the Log reports `Roster synced from sheet: N new, M refreshed`.
Google offers no push channel to a desktop app, so "live" means within one poll.

The database stores the two password columns in plaintext at the operator's
request. Treat `~/.autoshare/autoshare.db` and its `.bak-*` copies as
credentials.

```bat
IMPORT_ACCOUNTS.bat                              one-shot sync, sheet -> database
python scripts/import_accounts.py --dry-run      show what a sync would do
python scripts/import_accounts.py --xlsx FILE    import from a local .xlsx instead
python scripts/provision_profiles.py --dry-run   plan Brave profiles, then run without --dry-run
python scripts/login_accounts.py                 assisted login, one visible browser at a time
python scripts/login_accounts.py --unattended --batch 10 --pause 20
                                                 same, no prompts: skips any checkpoint, pauses between batches
python scripts/provision_profiles.py --rename-from-roster
python scripts/sync_sheet_status.py              rewrite the sheet's STATUS column from the database
```

Accounts Facebook has disabled are marked during login and skipped afterwards;
`python scripts/provision_profiles.py --purge-disabled --dry-run` shows what
`--purge-disabled` would remove.

## Utility scripts

| Launcher | Script | Purpose |
|---|---|---|
| `CHECK_FRIENDSHIPS.bat` | `scripts/check_friendships.py` | Friendship status for every saved profile, from the local database |
| | `scripts/check_login_status.py` | Live login scan of all Brave profiles; detects the "See more on Facebook" dialog a URL check misses |
| `CONFIGURE_DELAYS.bat` | `scripts/configure_delays.py` | Edit the anti-spam delays |
| `INSTALL.bat` | `scripts/diagnose_and_fix.py` | Install or repair dependencies; `--check` only reports |
| | `scripts/sync_sheet_status.py` | Rewrite the sheet's STATUS column (located by header) from the database |
| | `verify.py` | Proof harness: compiles every module, imports all of them, builds the window and asserts the callback wiring |

## Layout

```
main.py              entry point (RUN_APP.bat)
verify.py            proof harness
requirements.txt     the only dependency list; INSTALL.bat reads it
*.bat                double-click launchers; each one runs a script below
scripts/             operator tools: roster import, profile provisioning,
                     assisted login, status checks, delay config, CLI
docs/                delay-settings.md
src/app.py           builds DriverManager + MainWindow and wires the log
src/core/            DriverManager (one asyncio worker behind a command queue)
                     FacebookAutomation (Playwright driving)
                     memory_tracker
src/storage/         config_manager, SQLite database, storage_state cache,
                     sheets_api (Google Sheets REST), roster_sheet (sheet -> accounts sync)
src/ui/              two-tab window over five tab classes, theme, effects
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
