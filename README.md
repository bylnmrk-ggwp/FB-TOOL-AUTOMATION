# AutoShare — Facebook Post Sharer

Desktop tool that shares Facebook posts to groups and timelines, adds reactions
and comments, and manages friend connections across several accounts. It drives
your existing Brave browser profiles through Playwright, so each account stays
logged in and you never re-enter credentials.

Tkinter GUI, Python 3.12+, Windows.

## Install

```bat
FINAL_INSTALL.bat
```

Installs `playwright`, `Pillow`, `groq`, downloads the Chromium runtime, then
runs `check_status.py` to confirm every dependency imports. If something is
already broken, `INSTALL_DEPENDENCIES.bat` runs `diagnose_and_fix.py` instead.

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

`cli.py` covers the same operations without the GUI:

```bat
python cli.py share <post_url> <group_url>
python cli.py share-timeline <post_url>
python cli.py login <email> <password>
python cli.py batch
```

`python cli.py --help` lists every subcommand.

## Anti-spam delays

Every delay between shares, comments and navigations is configurable and exists
to protect the accounts. Do not set them to zero.

```bat
CONFIGURE_DELAYS.bat
```

Full reference: [DELAY_SETTINGS_README.md](DELAY_SETTINGS_README.md).

## Utility scripts

| Script | Purpose |
|---|---|
| `CHECK_FRIENDSHIPS.bat` → `check_friendships_simple.py` | Friendship status for every saved profile, read from the local database |
| `check_login_status.py` | Live login scan of all Brave profiles; detects the "See more on Facebook" dialog that a URL check alone misses |
| `check_status.py` | Dependency check plus an app-import smoke test |
| `diagnose_and_fix.py` | Repairs a broken dependency install |
| `verify.py` | Proof harness: compiles every module, imports all of them, builds the window and asserts the callback wiring |

## Layout

```
main.py              entry point
src/app.py           builds DriverManager + MainWindow and wires the log
src/core/            DriverManager (one asyncio worker behind a command queue)
                     FacebookAutomation (Playwright driving)
                     memory_tracker
src/storage/         config_manager, SQLite database, storage_state cache
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
