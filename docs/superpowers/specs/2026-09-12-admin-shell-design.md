# Admin shell, dashboard, and pending-login — design

Date: 2026-09-12
Status: approved (supersedes the shell section of
`2026-09-11-ui-relayout-design.md`; its Phase A foundation — spacing/type
scales, Segoe UI, DPI awareness, status bar, ScrollFrame — is kept as built)

## Problem

Three requests from the operator, in one release:

1. A button that finds every roster row whose Google Sheet `STATUS` cell is
   blank and logs those accounts in, writing the verdict back to the sheet.
2. A re-layout in the style of a web admin panel: left sidebar with the
   company logo and the section navigation, a dashboard landing page, and a
   professional look in both themes.
3. Motion: smooth transitions when switching pages, pressing buttons,
   collapsing the sidebar, and toggling light/dark.

The current shell (Phase A) is a top bar with three text nav buttons, the
whole `ProfilesTab` living in a left rail on every section, and a bottom log
drawer. Its open defects still stand: there is no selection model, so the
"Logged in only" filter (`profiles_tab.py:455-462`) does not govern what the
bulk actions target (`:524, :585, :614, :627, :641, :1012`); the profile and
roster lists are height-frozen `tk.Listbox` widgets with space-padded
columns; and nothing in the app reads the sheet's `STATUS` column back, so
"blank status" is not a fact the app can currently state.

## Shell

```
┌────────────┬──────────────────────────────────────────────┐
│  [LOGO]    │ Dashboard                     ☾   ⎋ Log Out  │  page header
│            ├──────────────────────────────────────────────┤
│ ▣ Dashboard│                                              │
│ ◉ Accounts │  page body — one page raised at a time       │
│ ≡ Queue    │                                              │
│ ✎ Compose  │                                              │
│ ◔ Monitor  │                                              │
│ ▤ Log      │                                              │
│            │                                              │
│ ‹ Collapse │                                              │
├────────────┴──────────────────────────────────────────────┤
│ Ready — Rene: sharing  ▓▓▓▓░░ 37/140   12 sel · RAM 8.6 GB│  status bar
└───────────────────────────────────────────────────────────┘
```

- **Sidebar** (`src/ui/sidebar.py`, class `Sidebar(ttk.Frame)`): logo block,
  nav items, collapse toggle. Expanded width 220 px, collapsed 56 px (icons
  only, tooltip on hover). State persists as config `ui_sidebar_collapsed`.
  API: `add_item(key, label, glyph)`, `set_active(key)`, `set_on_select(cb)`,
  `set_collapsed(bool, animate=True)`, `apply_theme(colors)`.
- **Logo**: `src/ui/assets/logo_light.png` in light mode, `logo_dark.png` in
  dark mode, rendered at sidebar width minus padding, aspect preserved
  (Pillow resize, cached per width). The operator supplies both PNGs with
  transparent backgrounds. When a file is missing the sidebar shows a text
  wordmark `MCARS` + `PH.` in brand colours so the shell never breaks.
- **Page header**: page title (`display` type scale) on the left; theme
  toggle and Log Out on the right; a `N selected` chip appears on Queue and
  Compose when the selection is non-empty.
- **Content host**: pages are frames in one grid cell, raised with
  `tkraise`. Page registry is one list of `(key, title, glyph, factory)` in
  `MainWindow`, replacing the two hardcoded literals that had to be kept in
  sync.
- **Log drawer removed.** Log is a page. The status bar's activity line keeps
  showing the live progress message, and the Dashboard shows recent alerts.
- **Status bar** unchanged from Phase A, plus the selection count.
- Window minsize stays `px(1100) × px(700)`; sidebar collapses automatically
  below `px(1200)` body width and expands again above it unless the operator
  pinned a state.

## Pages

### Dashboard (`src/ui/dashboard_page.py`)

Row 1, four stat cards: **Total accounts**, **Logged in**, **Need login**,
**Disabled**. Numbers animate (count-up, 300 ms) when they change. Under the
cards: primary button **Log in N pending accounts** (disabled at N = 0 or
while a run is active) and a muted line `M pending rows have no Brave profile
— run provision_profiles.py`.

Row 2, three cards:

- **Run activity** — the current run's progress bar and `done/total`, the
  active profile line, and the last completed run's summary (`132 ok · 8
  failed · 20:11`). The summary persists in config `last_run_summary` so it
  survives a restart.
- **System** — RAM used/total, browser process count, active sessions
  (profiles with status `ok`), and `Sheet synced 12 s ago` from the
  watcher's last successful poll.
- **Recent alerts** — the last 8 log lines tagged `error`, newest first,
  each with its `HH:MM:SS`. Clicking the card opens the Log page.

Data sources: `db.count_accounts`, `db.count_disabled`, `db.logged_in_profiles`,
the new `db.count_pending()`, `memory_tab` stats via the existing
`set_on_stats` hook, `log_tab` via a new `set_on_alert(cb)` hook, and
`MainWindow._handle_result` for run progress. The page refreshes when raised
and every 5 s while visible.

### Accounts (`src/ui/accounts_page.py`, replaces `profiles_tab.py`)

One `ttk.Treeview` table, filling the page height:

| col | content |
|---|---|
| `☑` | checkbox glyph, toggled by click; header click toggles all visible |
| `#` | `sheet_no` |
| Name | `facebook_name` |
| Username | `username` |
| Brave profile | `linked_profile` or `—` |
| Status | `● Logged in` / `○ Not logged in` / `○ Pending` / `✕ Disabled` / `⚠ Rate limited` |
| Reason | `status_reason` |

Toolbar above the table: search entry (filters Name / Username / Brave
profile / Gmail), status filter (`All · Logged in · Needs login · Pending ·
Disabled`), `Select all` / `Clear`. Filter and search persist in config.

Action bar below: `Log in selected` · `Check login status` · `Auto setup` ·
`Accept friend requests` · `Update FB names` · `Add Brave profile` · `Scan` ·
`Launch` · `Remove` · `Link / Unlink`. Each acts on the checked rows;
single-row actions (Launch, Remove, Link, Unlink, Update FB name) enable
only when exactly one row is checked. Buttons that run a job disable while
it runs and re-enable on the result, as today.

Selection model: `selected_accounts() -> list[dict]` and
`selected_profiles() -> list[str]` (checked rows that have a linked Brave
profile). `MainWindow` passes the page to `QueueTab` and `ShareTab` through
`set_selection_source(page)`; every handler that enumerated
`cfg.list_profiles()` now reads `selected_profiles()`, and their button
labels drop `(All Profiles)`. An empty selection means "all logged-in
profiles", stated in the header chip as `all logged in (N)` so the operator
always sees the scope.

Everything the old tab did survives: the Brave picker dialog, FB-name fetch
(kept on its ad-hoc thread — moving it behind `cmd_queue` stays a separate
task, as recorded in the 2026-09-10 audit), roster link/unlink, rate-limit
marks. `MainWindow.profiles_tab` remains as an alias of the page so
`verify.py`'s wiring proofs and the `set_on_*` hooks keep their names.

### Queue, Compose, Monitor, Log

`QueueTab`, `ShareTab`, `MemoryMonitorTab`, `LogTab` are hosted as pages.
Their only change is the selection source above. Merging the three quick-add
forms with the share form (the old Phase C) stays deferred.

## Pending login

### Reading the sheet's STATUS column

`roster_sheet.HEADERS` gains `"STATUS": "sheet_status"`. `parse_accounts`
fills it (`""` when the header or cell is absent). `database.upsert_account`
stores it in a new `accounts.sheet_status TEXT NOT NULL DEFAULT ''` column
(added by `_migrate`). The 20 s `SheetWatcher` therefore mirrors the cell
continuously. `linked_profile`, `status`, `status_reason` stay machine-owned
and untouched by the sync; `sheet_status` is sheet-owned and never written
by the app except through the existing sheet writers.

`db.pending_accounts() -> list[dict]`: rows with `sheet_status == ''` and
`status != 'disabled'`. `db.count_pending() -> tuple[int, int]`: (pending,
pending without a linked profile).

### The command

`DriverManager.login_accounts(usernames: list[str])` enqueues
`{"type": "login_accounts", "usernames": [...]}`. `_do_login_accounts`:

1. Preflight. Refuse with `login_accounts_result{ok: False, error}` when a
   batch or watch is running, or when `brave.exe` is running (the shared
   User Data dir is locked; the same check `scripts/login_accounts.py:533`
   makes).
2. For each username, in roster order: resolve the account; if it has no
   `linked_profile`, append to `skipped` with reason `no Brave profile` and
   continue. Otherwise write `LOGGING IN` to its sheet cell
   (`sheet_status.mark_in_progress(username)`, a new thin wrapper over
   `write_status` that resolves gid/columns/row index once per run and is
   called through `asyncio.to_thread`), then `await
   self._relogin_profile(profile_name)`. That existing coroutine logs in
   headless inside the real Brave user-data-dir, records the verdict with
   `_record_and_publish`, and pushes the sheet cell. The cooldown gate
   `_relogin_allowed` is not consulted — the operator asked explicitly.
3. Emit `login_accounts_progress{username, profile_name, ok, message,
   current, total}` after each account; sleep `random.uniform(2, 4)` s.
4. Emit `login_accounts_result{ok: True, logged_in, failed: [(username,
   reason)], skipped: [(username, reason)]}`.

Checkpoint and 2FA cannot be solved headless; those accounts end as
`NOT LOGGED IN / CHECKPOINT...` on the sheet and in `failed`, and the final
log block lists them so the operator can finish them with
`scripts/login_accounts.py --only <username>`.

`MainWindow._handle_result` handles the two new types: progress feeds the
status-bar activity line, the Accounts table row, and the log; the result
re-enables the buttons, refreshes Dashboard and Accounts, and writes a
banner block to the log.

Entry points: Dashboard **Log in N pending accounts** (all pending with a
profile) and Accounts **Log in selected** (checked rows, pending or not).

## Motion

There is no third-party animation framework for Tkinter: ttkbootstrap and
CustomTkinter restyle widgets but animate nothing, and Qt would mean
rewriting the whole UI layer. The framework is therefore a small tween
engine in `src/ui/effects.py` that every animation runs on:

```python
tween(widget, duration_ms, step, done=None, easing=ease_out_cubic)
```

`step(t)` receives eased progress 0..1 on a `widget.after(16, ...)` clock;
the tween cancels itself when the widget is destroyed, and a second tween on
the same widget and key replaces the first. Config `ui_animations` (default
on) makes every tween jump straight to its end state when off.

| trigger | effect | duration |
|---|---|---|
| page switch | new page slides in from +24 px (x) to 0 via `place`, then is re-gridded; nav active indicator moves | 160 ms |
| sidebar collapse / expand | width tween 220 ↔ 56; labels hide at < 120 px | 180 ms |
| button press | on `<ButtonRelease-1>` the button's background tweens from the pressed colour back to its resting colour (per-button dynamic ttk style) | 150 ms |
| theme toggle | window alpha 1.0 → 0.35 (80 ms), theme applied at the low point, alpha → 1.0 (140 ms) — Tk cannot fade individual widgets, so the whole window dips | 220 ms |
| dashboard numbers | count-up from previous to new value | 300 ms |
| status-bar progress | value tween between reported steps | 200 ms |
| nav / list hover | background tint via style map (already instant); no tween | — |

## Visual system

- Palette keys added to both themes: `sidebar_bg`, `sidebar_fg`,
  `sidebar_muted`, `sidebar_active_bg`, `sidebar_hover_bg`, `brand`
  (`#d1202a` light, `#e2323c` dark). Existing keys keep their names.
- Accent stays indigo for interactive controls. Brand red is used for the
  logo and the active-nav indicator bar only — a red primary button would
  read as the error colour.
- Nav glyphs from Segoe Fluent Icons (present on Windows 11); Unicode
  geometric fallback when the face is missing.
- Cards: `card` fill, no border, `SPACE["lg"]` padding, title in `title`
  scale, big number in `display` scale.

## Files

New: `src/ui/sidebar.py`, `src/ui/dashboard_page.py`,
`src/ui/accounts_page.py`, `src/ui/assets/` (logo PNGs — committed, they
are brand assets, not secrets).

Changed: `src/ui/main_window.py`, `src/ui/theme.py`, `src/ui/effects.py`,
`src/ui/queue_tab.py`, `src/ui/share_tab.py`, `src/ui/log_tab.py`,
`src/core/driver_manager.py`, `src/storage/roster_sheet.py`,
`src/storage/database.py`, `src/storage/sheet_status.py`, `verify.py`,
`README.md`.

Removed: `src/ui/profiles_tab.py`, once `accounts_page.py` carries every
hook `verify.py` asserts.

## Build order

1. **Shell + motion**: `theme.py` keys, `effects.tween`, `sidebar.py`, new
   `main_window.py` shell hosting the five existing tabs as pages plus a
   placeholder Dashboard; logo loading; all four shell animations.
2. **Pending login**: `sheet_status` mirror (roster_sheet, database
   migration), `db.pending_accounts`, `sheet_status.mark_in_progress`,
   `DriverManager.login_accounts`, result handling, Dashboard page for real.
3. **Accounts page + selection**: `accounts_page.py`, selection source in
   Queue/Compose, label cleanup, delete `profiles_tab.py`.

Each step ends with `python verify.py` printing `ALL PROOFS PASS` and a
screenshot pass at `1100×700` and `1920×1080`, light and dark, every page,
sidebar expanded and collapsed. Step 2 also runs the pending scan against
the live sheet in a dry mode (list only, no browser) and checks the count
matches a manual look at the sheet.

## Non-goals

- Merging the quick-add forms into one composer (old Phase C).
- Moving `fetch_facebook_name_sync` behind `cmd_queue`.
- Provisioning Brave profiles from the GUI; pending rows without a profile
  are reported, not provisioned.
- Any third-party UI library; styling stays hand-rolled ttk in `theme.py`.
