# UI re-layout — design

Date: 2026-09-11
Status: approved, Phase A in progress

## Problem

The window is organised by implementation module — Profiles, Queue, Share,
Memory, Log — rather than by the work the operator does. An 11-agent read of
`src/ui/` found 82 persistent controls, 20 layout defects and 14 duplicated
control groups across 5,200 lines.

One root cause explains most of them: **there is no selection model.** Scope
lives in button labels (`(All Profiles)`, `(This Profile)`,
`(All URLs — All Accounts)`) instead of in a set of selected profiles. So every
scope needs its own button and every form needs its own copy of the same
fields — five Post-URL entries, four comment widgets, three reaction pickers,
and two byte-identical `Add to Queue (All Profiles)` buttons that perform
different actions (`queue_tab.py:154-157` and `:194-197`).

The same gap causes a correctness bug. The "Logged in only" checkbox filters
the visible list through `_visible_profiles` (`profiles_tab.py:455-462`), but
every action handler enumerates the unfiltered `cfg.list_profiles()`
(`:524, :585, :614, :627, :641, :1012`). The operator sees twelve logged-in
accounts, presses "Setup All Profiles", and the run targets all of them —
including logged-out and rate-limited accounts. Nothing on screen signals the
mismatch.

Three further defects cost the operator directly during a run:

- The progress bar and status line are the last children of the Queue tab's
  scroll surface (`queue_tab.py:483-491`). During a 140-profile run the
  operator must scroll to the bottom and stay there to see progress.
- The Log is a `weight=1` pane draggable to zero height with no control
  anywhere to restore it (`main_window.py:330-331`).
- Every list is height-frozen inside a canvas that manages only width, so a
  maximised window adds blank scroll space instead of rows. The queue list is
  permanently 8 rows, the profile list 6, the roster 10.

## Target shell

```
┌──────────────────────────────────────────────────────────────┐
│ AutoShare   [ Queue ][ Compose ][ Monitor ]    Log Out │ ☾    │  top bar
├─────────────┬────────────────────────────────────────────────┤
│ PROFILES    │  content host — one section raised at a time   │
│ rail        │                                                │
│ 240–360px   │                                                │
├─────────────┴────────────────────────────────────────────────┤
│ ▾ Log                                    Autoscroll ☑  Save  │  drawer
├──────────────────────────────────────────────────────────────┤
│ Ready — Rene: sharing   ▓▓▓▓░░ 37/140   3 sel · RAM 8.6/17.9 │  status bar
└──────────────────────────────────────────────────────────────┘
```

Sections replace the two notebook tabs and are raised with `tkraise`, not a
`ttk.Notebook`. The rail is the selection model every action reads. Progress
and memory live in the status bar, visible from every section. The log drawer
has a toggle that is always reachable.

## Foundation

`theme.py` gains the scales it never had. There are currently eleven inline
padding tuples in `main_window.py` alone and four per-tab `pad={}` dicts that
have drifted apart.

```python
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
TYPE  = {"micro": 8, "small": 9, "body": 10, "title": 12, "display": 18}
```

Typeface changes from Poppins to Segoe UI. Measured at 10pt over five real
labels from this UI, Segoe UI is 9.0% narrower (956px vs 1051px) and its
linespace is 26% shorter (17px vs 23px). The linespace is the larger win: at
an unchanged pixel height a profile list shows eight rows instead of six.
Poppins is a geometric display face — wide, monoline, single-storey `a` — and
is unhinted at 10pt. Segoe UI is the native Windows UI face, ClearType-hinted
across 9–12pt. Monospace preference becomes Cascadia Mono, then Consolas.

The app is DPI-unaware. On a 1920×1080 display at 125% scaling Windows
bitmap-stretches the whole window, so every glyph is resampled.
`SetProcessDpiAwareness(1)` is called before `Tk()`. Level 1 (system DPI
aware), not level 2: measured on this display both levels give Tk the same
120 DPI and the same 23px Segoe UI linespace, but Tk 8.6 has no per-monitor
rescale path, so level 2 would leave the window mis-sized after a move
between monitors of different scale. With awareness on, Tk scales point-sized
fonts itself; window geometry in pixels is multiplied by the measured DPI
ratio so the window keeps its physical size.

Dead code removed: seven palette keys per mode with no consumer, five ttk
styles that are configured on every theme switch but never applied, and the
`TSpinbox` style for a widget class instantiated zero times.

Ghost buttons gain a resting 1px border. Today they carry no fill and no
border, so `Update FB Name`, `Launch Profile` and `Remove` read as disabled.

## Phases

Phase A is the approved unit of work. B and C are described so the phase
boundaries are deliberate, and each is re-approved before it starts.

### Phase A — shell and foundation

Touches `theme.py`, `main.py`, `main_window.py`, `scroll_container.py`, and
one added hook in `memory_monitor.py`. The five tab classes render inside the
new shell **unchanged**; their public APIs are untouched.

- spacing and type scales, Segoe UI, Cascadia Mono, dead-token removal
- DPI awareness
- new shell: top bar, rail host, content host, log drawer, status bar
- status bar gains a progress bar and a RAM readout
- `ScrollFrame` gains fill-to-viewport height management and scrollbar
  auto-hide; the three hand-rolled copies in `queue_tab.py:49-78`,
  `share_tab.py:47-68` and `image_picker.py:90-113` are replaced by it.
  Horizontal scrolling is deferred to Phase C: every current surface is a
  vertical stack of forms whose width is pinned to the viewport on purpose,
  and the only content that needs a horizontal path is the queue table that
  Phase C introduces.

In Phase A the rail hosts `ProfilesTab` as-is and the three sections host
`QueueTab`, `ShareTab` and `MemoryMonitorTab`. Splitting `ProfilesTab` into a
rail and an Accounts body is Phase B/C work.

### Phase B — selection model

Extract the profile list, search and filter into `src/ui/profile_rail.py`
exposing `selected_profiles()`. Rewire every action to read it. This is what
fixes the filter/action mismatch and removes `(All Profiles)` from labels.

### Phase C — content sections

Merge the three quick-add forms and the share form into one composer. Let the
queue, roster and memory lists grow. Move the log into the drawer properly,
with correct line counting and an autoscroll pause.

## Verification

Each phase must end with:

- `python verify.py` printing `ALL PROOFS PASS`. It asserts that
  `profiles_tab`, `queue_tab`, `share_tab`, `memory_tab` and `log_tab` still
  exist on `MainWindow` and that every `set_on_*` hook a tab exposes has been
  wired. Those five attribute names are therefore preserved throughout.
- A screenshot pass at 1100×700 (the minsize) and 1920×1080, in light and
  dark, confirming no control is clipped and no section is collapsed.

## Non-goals

Behaviour is not changed in Phase A: no handler is rewritten, no command is
added or removed, and no control is dropped. The blocking-call violations in
`profiles_tab.py` and the modal raised from inside the result poll
(`main_window.py:816-822`) are real defects but belong to a separate task.
