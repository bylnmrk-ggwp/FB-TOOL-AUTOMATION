# Admin Shell, Dashboard, and Pending-Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Tkinter shell as a web-admin layout (logo sidebar, page header, dashboard), animate its transitions, and add a one-click "log in every account whose sheet STATUS is blank" command.

**Architecture:** `MainWindow` becomes a thin shell: a `Sidebar` on the left, a page header and a content host on the right, the Phase A status bar at the bottom. Pages are the existing tab classes plus two new ones (`DashboardPage`, `AccountsPage`). Motion is a single `effects.tween()` clock. The pending-login command follows the existing pattern: UI enqueues a dict on `DriverManager.cmd_queue`, the worker emits `*_progress` / `*_result` dicts, `MainWindow._poll_queue` applies them.

**Tech Stack:** Python 3.12+, Tkinter/ttk (hand-rolled styles in `src/ui/theme.py`), Pillow (logo), Playwright via the existing `DriverManager`, SQLite, Google Sheets REST via `src/storage/sheets_api.py`.

**Spec:** `docs/superpowers/specs/2026-09-12-admin-shell-design.md`

## Global Constraints

- No third-party UI library; every style is configured in `MainWindow._apply_theme` from palette keys in `src/ui/theme.py`. Do not rename existing palette keys.
- Fonts and paddings come from `theme.font()` / `theme.mono()` / `theme.SPACE` — no new inline `(theme.UI_FONT, 10)` tuples.
- All mousewheel scrolling goes through `effects.install_wheel_router()`; never `bind_all("<MouseWheel>")` elsewhere.
- Every Facebook action goes through `DriverManager.cmd_queue`; the UI never blocks on a thread. (`fetch_facebook_name_sync` on its ad-hoc thread is a known, accepted exception — do not touch it.)
- `MainWindow` must keep attributes `profiles_tab`, `queue_tab`, `share_tab`, `memory_tab`, `log_tab`; every `set_on_*` a page exposes must be wired (`verify.py` asserts both).
- The proof harness is `python verify.py` printing `ALL PROOFS PASS`. There is no pytest. Each task adds its proof to `verify.py` first, watches it fail, then implements.
- Windows only. Screen for screenshots is 1920×1080 at 125 % (Tk px ratio 1.25).
- Never `git add .` or `git add -A` — the working directory holds a plaintext account spreadsheet. Stage explicit paths.
- Commit messages: `type: what changed and why`, one line, no trailer.

---

## File map

| file | responsibility |
|---|---|
| `src/ui/theme.py` | palettes (+ sidebar/brand keys), `MOTION` durations |
| `src/ui/effects.py` | `tween`, `blend`, `slide_in`, `animate_press`, `count_up`, animation switch |
| `src/ui/sidebar.py` | `Sidebar`: logo, nav items, collapse, tooltips |
| `src/ui/main_window.py` | shell: sidebar + header + content host + status bar; page registry; result dispatch |
| `src/ui/dashboard_page.py` | `DashboardPage`: stat cards, pending-login button, run/system/alerts cards |
| `src/ui/profile_dialogs.py` | Brave picker, saved-profile picker, FB-name fetch dialogs (moved out of `profiles_tab.py`) |
| `src/ui/accounts_page.py` | `AccountsPage`: Treeview table, filters, action bar, selection model |
| `src/ui/queue_tab.py`, `src/ui/share_tab.py` | read the selection source; labels lose `(All Profiles)` |
| `src/ui/log_tab.py` | `set_on_alert` hook |
| `src/storage/roster_sheet.py` | mirror `STATUS` header into `sheet_status`; watcher `last_ok` |
| `src/storage/database.py` | `sheet_status` column, `pending_accounts`, `count_pending` |
| `src/storage/sheet_status.py` | `SheetWriter` (resolve once, write many, `mark_in_progress`) |
| `src/core/driver_manager.py` | `login_accounts` command; `profile_names` on bulk commands |
| `scripts/screenshot_ui.py` | operator tool: every page × theme × size × sidebar state to PNG |
| `verify.py` | proofs |

---

## Task 1: Theme keys and motion durations

**Files:**
- Modify: `src/ui/theme.py` (THEMES dict at lines 120-253; add `MOTION` after `TYPE`)
- Modify: `verify.py` (append proof)

**Interfaces:**
- Produces: palette keys `sidebar_bg`, `sidebar_fg`, `sidebar_muted`, `sidebar_active_bg`, `sidebar_active_fg`, `sidebar_hover_bg`, `sidebar_border`, `brand`, `header_bg`, `chip_bg`, `chip_fg` in both themes; `theme.MOTION = {"page": 160, "sidebar": 180, "press": 150, "theme": 220, "count": 300, "progress": 200}`.

- [ ] **Step 1: Add the proof to `verify.py`**

Append before the `print("\n================ RESULT ================")` line:

```python
step("theme keys")
from src.ui import theme as _theme
_NEW_KEYS = ("sidebar_bg", "sidebar_fg", "sidebar_muted", "sidebar_active_bg",
             "sidebar_active_fg", "sidebar_hover_bg", "sidebar_border", "brand",
             "header_bg", "chip_bg", "chip_fg")
for _mode in ("light", "dark"):
    for _k in _NEW_KEYS:
        if _k not in _theme.THEMES[_mode]:
            failures.append(f"theme.THEMES[{_mode!r}] missing {_k!r}")
if set(_theme.THEMES["light"]) != set(_theme.THEMES["dark"]):
    failures.append("light/dark palettes have different key sets")
for _k in ("page", "sidebar", "press", "theme", "count", "progress"):
    if not isinstance(getattr(_theme, "MOTION", {}).get(_k), int):
        failures.append(f"theme.MOTION[{_k!r}] missing")
print("ok" if not [f for f in failures if "theme" in f] else "FAILED")
```

- [ ] **Step 2: Run `python verify.py`** — expect `FAIL: theme.THEMES['light'] missing 'sidebar_bg'` and the MOTION lines.

- [ ] **Step 3: Add the keys**

In `THEMES["light"]`, after `"scroll_thumb_hover": "#a1a1aa",`:

```python
        # Sidebar (web-admin shell) and brand
        "sidebar_bg": "#ffffff",
        "sidebar_fg": "#3f3f46",
        "sidebar_muted": "#71717a",
        "sidebar_active_bg": "#f4f4f5",
        "sidebar_active_fg": "#09090b",
        "sidebar_hover_bg": "#f4f4f5",
        "sidebar_border": "#e7e7ea",
        "brand": "#d1202a",
        "header_bg": "#fafafa",
        "chip_bg": "#eef2ff",
        "chip_fg": "#312e81",
```

In `THEMES["dark"]`, after `"scroll_thumb_hover": "#52525b",`:

```python
        "sidebar_bg": "#131316",
        "sidebar_fg": "#a1a1aa",
        "sidebar_muted": "#71717a",
        "sidebar_active_bg": "#1f1f24",
        "sidebar_active_fg": "#fafafa",
        "sidebar_hover_bg": "#1a1a1e",
        "sidebar_border": "#27272a",
        "brand": "#e2323c",
        "header_bg": "#0f0f11",
        "chip_bg": "#26264a",
        "chip_fg": "#e4e4e7",
```

After the `TYPE` dict:

```python
# Motion durations in milliseconds. One place, so the whole UI feels like
# one system; effects.tween() reads these through the callers.
MOTION = {
    "page": 160,      # page slide-in on navigation
    "sidebar": 180,   # sidebar collapse / expand
    "press": 150,     # button release pulse
    "theme": 220,     # light/dark dip (80 out, 140 in)
    "count": 300,     # dashboard number count-up
    "progress": 200,  # status-bar progress value
}
```

- [ ] **Step 4: Run `python verify.py`** — expect `ALL PROOFS PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/ui/theme.py verify.py
git commit -m "feat: sidebar and brand palette keys, motion durations"
```

---

## Task 2: Tween engine in `effects.py`

**Files:**
- Modify: `src/ui/effects.py` (append a new section at the end)
- Modify: `verify.py` (append proof)

**Interfaces:**
- Produces:
  - `effects.ease_out_cubic(t: float) -> float`, `effects.linear(t) -> float`
  - `effects.animations_enabled() -> bool` (config `ui_animations`, default on; `effects.set_animations_override(value: bool | None)` forces it for proofs)
  - `effects.tween(widget, duration_ms: int, step, done=None, easing=ease_out_cubic, key: str = "default") -> None` — `step(t)` gets eased 0..1; a new tween with the same `(widget, key)` cancels the old one; when animations are off, `step(1.0)` then `done()` run synchronously
  - `effects.cancel_tweens(widget)`
  - `effects.blend(hex_a: str, hex_b: str, t: float) -> str`
  - `effects.slide_in(frame, dx: int = 24, duration_ms: int = 160, done=None)` — frame must be a grid child at `row=0, column=0`
  - `effects.animate_press(button: ttk.Button)` — binds a release pulse; returns the button
  - `effects.count_up(label, start: int, end: int, duration_ms: int, fmt=lambda v: f"{v:,}")`

- [ ] **Step 1: Add the proof**

Append to `verify.py` before the RESULT block:

```python
step("effects.tween")
import tkinter as _tk
from src.ui import effects as _fx
_root = _tk.Tk(); _root.withdraw()
_seen = []
_fx.set_animations_override(True)
_fx.tween(_root, 60, lambda t: _seen.append(t), done=lambda: _seen.append("done"),
          easing=_fx.linear)
_t0 = _root.after(400, _root.quit); _root.mainloop(); _root.after_cancel(_t0)
if not _seen or _seen[-1] != "done" or _seen[-2] != 1.0 or len(_seen) < 3:
    failures.append(f"tween did not run to completion: {_seen}")
if any(_seen[i] > _seen[i + 1] for i in range(len(_seen) - 2)):
    failures.append(f"tween not monotonic: {_seen}")
_seen.clear(); _fx.set_animations_override(False)
_fx.tween(_root, 60, lambda t: _seen.append(t), done=lambda: _seen.append("done"))
if _seen != [1.0, "done"]:
    failures.append(f"tween with animations off must be synchronous: {_seen}")
if _fx.blend("#000000", "#ffffff", 0.5) != "#808080":
    failures.append(f"blend wrong: {_fx.blend('#000000', '#ffffff', 0.5)}")
if _fx.ease_out_cubic(0) != 0 or _fx.ease_out_cubic(1) != 1:
    failures.append("ease_out_cubic endpoints")
_fx.set_animations_override(None); _root.destroy()
print("ok" if not [f for f in failures if "tween" in f or "blend" in f or "ease" in f] else "FAILED")
```

- [ ] **Step 2: Run `python verify.py`** — expect a traceback / `AttributeError: module 'src.ui.effects' has no attribute 'set_animations_override'` reported as a failure.

- [ ] **Step 3: Implement**

Append to `src/ui/effects.py`:

```python
# ── Motion ──────────────────────────────────────────────────
#
# One clock for every animation in the UI. Tk has no compositor: a widget
# cannot fade, so everything here is a geometry, colour or value tween on
# widget.after(). Duration comes from theme.MOTION at the call site.

_ANIM_OVERRIDE: bool | None = None
_TWEENS: dict[tuple[int, str], str] = {}


def linear(t: float) -> float:
    return t


def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def set_animations_override(value: bool | None) -> None:
    """Force animations on/off (proofs and screenshots); None = config."""
    global _ANIM_OVERRIDE
    _ANIM_OVERRIDE = value


def animations_enabled() -> bool:
    if _ANIM_OVERRIDE is not None:
        return _ANIM_OVERRIDE
    from src.storage import config_manager as cfg
    return cfg.get_setting("ui_animations", True) in (True, 1, "1", "true")


def cancel_tweens(widget) -> None:
    wid = id(widget)
    for key in [k for k in _TWEENS if k[0] == wid]:
        try:
            widget.after_cancel(_TWEENS.pop(key))
        except Exception:
            _TWEENS.pop(key, None)


def tween(widget, duration_ms: int, step, done=None,
          easing=ease_out_cubic, key: str = "default") -> None:
    """Drive step(t) from 0 to 1 over duration_ms on widget's after() clock.

    A second tween with the same (widget, key) replaces the first, so a
    click during a slide restarts the slide instead of stacking two. When
    animations are off the end state is applied at once, so callers never
    branch on the setting.
    """
    k = (id(widget), key)
    old = _TWEENS.pop(k, None)
    if old is not None:
        try:
            widget.after_cancel(old)
        except Exception:
            pass
    if duration_ms <= 0 or not animations_enabled():
        step(1.0)
        if done:
            done()
        return
    start = time.monotonic()

    def frame():
        t = min(1.0, (time.monotonic() - start) * 1000.0 / duration_ms)
        try:
            step(easing(t))
        except tk.TclError:
            _TWEENS.pop(k, None)
            return
        if t >= 1.0:
            _TWEENS.pop(k, None)
            if done:
                done()
            return
        try:
            _TWEENS[k] = widget.after(16, frame)
        except tk.TclError:
            _TWEENS.pop(k, None)

    frame()


def blend(hex_a: str, hex_b: str, t: float) -> str:
    """Linear mix of two #rrggbb colours, t=0 gives hex_a."""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def slide_in(frame, dx: int = 24, duration_ms: int = 160, done=None) -> None:
    """Raise a page with a short slide from the right.

    The page is a grid child at (0, 0) of a host that fills its cell. It is
    lifted out of grid, placed over the host at x=dx, tweened to x=0, then
    re-gridded so resizing keeps working with no place() residue.
    """
    frame.grid_remove()
    frame.place(x=dx, y=0, relwidth=1.0, relheight=1.0)
    frame.tkraise()

    def step(t):
        frame.place_configure(x=int(round(dx * (1.0 - t))))

    def finish():
        frame.place_forget()
        frame.grid(row=0, column=0, sticky="nsew")
        frame.tkraise()
        if done:
            done()

    tween(frame, duration_ms, step, done=finish, key="slide")


def animate_press(button, duration_ms: int = 150):
    """Fade a ttk.Button's background from its pressed colour back to rest
    after a click, so the press reads as a pulse rather than a flicker.

    Uses a per-button derived style ("P<id>.<base>") so no other button is
    affected; the style inherits everything else from its base.
    """
    def on_release(_event=None):
        base = button.cget("style") or "TButton"
        if base.startswith("P") and "." in base and base.split(".", 1)[0][1:].isdigit():
            base = base.split(".", 1)[1]
        style = ttk.Style(button)
        rest = style.lookup(base, "background") or theme.get()["secondary"]
        pressed = style.lookup(base, "background", ("pressed",)) or rest
        if pressed == rest:
            return
        dyn = f"P{id(button)}.{base}"
        style.configure(dyn, background=pressed)
        button.configure(style=dyn)

        def step(t):
            style.configure(dyn, background=blend(pressed, rest, t))

        def finish():
            try:
                button.configure(style=base)
            except tk.TclError:
                pass

        tween(button, duration_ms, step, done=finish, key="press")

    button.bind("<ButtonRelease-1>", on_release, add="+")
    return button


def count_up(label, start: int, end: int, duration_ms: int,
             fmt=lambda v: f"{v:,}") -> None:
    """Tween a numeric label from start to end."""
    if start == end:
        label.configure(text=fmt(end))
        return

    def step(t):
        label.configure(text=fmt(int(round(start + (end - start) * t))))

    tween(label, duration_ms, step, key="count")
```

- [ ] **Step 4: Run `python verify.py`** — expect `ALL PROOFS PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/ui/effects.py verify.py
git commit -m "feat: tween engine for page, sidebar, press and count animations"
```

---

## Task 3: `Sidebar` widget and logo assets

**Files:**
- Create: `src/ui/sidebar.py`
- Create: `src/ui/assets/README.md`
- Modify: `verify.py` (append proof)

**Interfaces:**
- Consumes: `theme.get()`, `theme.MOTION["sidebar"]`, `effects.tween`, `effects.animations_enabled`
- Produces: `class Sidebar(tk.Frame)` with
  - `__init__(self, parent, px, expanded_px: int = 220, collapsed_px: int = 56)` — `px` is `MainWindow.px`
  - `add_item(key: str, label: str, glyph: str, fallback: str) -> None`
  - `set_active(key: str) -> None`
  - `set_on_select(cb)` — `cb(key)`
  - `set_collapsed(collapsed: bool, animate: bool = True) -> None`; `collapsed` property
  - `set_on_collapse(cb)` — `cb(collapsed: bool)` fires after the tween
  - `apply_theme(colors: dict) -> None` — recolours and reloads the logo for the mode
  - `LOGO_FILES = {"light": "logo_light.png", "dark": "logo_dark.png"}` resolved under `src/ui/assets/`
  - `Sidebar.glyph_font() -> tuple` — `("Segoe Fluent Icons", 12)` or `("Segoe MDL2 Assets", 12)` when available, else `None` (use fallback glyphs)

- [ ] **Step 1: Add the proof**

```python
step("sidebar")
from src.ui.sidebar import Sidebar as _Sidebar
_root = _tk.Tk(); _root.withdraw()
_fx.set_animations_override(False)
_sb = _Sidebar(_root, px=lambda n: n)
_sb.pack(side="left", fill="y")
_picked = []
_sb.set_on_select(_picked.append)
for _k, _l in (("dashboard", "Dashboard"), ("queue", "Queue")):
    _sb.add_item(_k, _l, "\uE80F", "\u25a3")
_sb.set_active("queue")
_root.update_idletasks()
if _sb.active != "queue":
    failures.append("sidebar.set_active did not stick")
_sb._items["dashboard"].event_generate("<Button-1>")
_root.update()
if _picked != ["dashboard"]:
    failures.append(f"sidebar select callback not fired: {_picked}")
_sb.set_collapsed(True, animate=False); _root.update_idletasks()
if _sb.winfo_reqwidth() != 56 or not _sb.collapsed:
    failures.append(f"sidebar collapsed width {_sb.winfo_reqwidth()}")
_sb.set_collapsed(False, animate=False); _root.update_idletasks()
if _sb.winfo_reqwidth() != 220:
    failures.append(f"sidebar expanded width {_sb.winfo_reqwidth()}")
for _mode in ("light", "dark"):
    _theme.set_mode(_mode); _sb.apply_theme(_theme.get())
_theme.set_mode("light")
_fx.set_animations_override(None); _root.destroy()
print("ok" if not [f for f in failures if "sidebar" in f] else "FAILED")
```

- [ ] **Step 2: Run `python verify.py`** — expect `ModuleNotFoundError: No module named 'src.ui.sidebar'` counted as a failure.

- [ ] **Step 3: Create `src/ui/assets/README.md`**

```markdown
# Brand assets

Drop the two logo files here, PNG with a transparent background:

- `logo_light.png` — black "MCARS" + red "PH." (shown in light mode)
- `logo_dark.png`  — white "MCARS" + red "PH."  (shown in dark mode)

The sidebar scales them to its width. When a file is missing it shows a
text wordmark instead, so the app never depends on these files to start.
```

- [ ] **Step 4: Create `src/ui/sidebar.py`**

```python
"""Left navigation sidebar for the admin-style shell.

Raw tk widgets, not ttk: every surface here is a flat colour that the theme
owns outright (sidebar_bg, sidebar_hover_bg, sidebar_active_bg), and ttk's
style maps cannot express "3 px brand bar on the active item".

Collapse tweens the frame width; labels are hidden below 120 px so the text
never clips mid-slide. Glyphs come from Segoe Fluent Icons (Windows 11) or
Segoe MDL2 Assets (Windows 10); a plain Unicode fallback is used elsewhere.
"""
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

from src.ui import effects, theme

ASSETS = Path(__file__).resolve().parent / "assets"
LOGO_FILES = {"light": "logo_light.png", "dark": "logo_dark.png"}
LABEL_MIN_WIDTH = 120


class Sidebar(tk.Frame):
    def __init__(self, parent, px, expanded_px: int = 220,
                 collapsed_px: int = 56, **kwargs):
        super().__init__(parent, **kwargs)
        self._px = px
        self._expanded = px(expanded_px)
        self._collapsed_w = px(collapsed_px)
        self._collapsed = False
        self._items: dict[str, tk.Frame] = {}
        self._parts: dict[str, dict] = {}
        self._active = None
        self._on_select = None
        self._on_collapse = None
        self._logo_img = None
        self._logo_cache: dict[tuple[str, int], object] = {}
        self._tip = None
        self._tip_after = None
        self._glyph_font = self.glyph_font()

        self.configure(width=self._expanded)
        self.pack_propagate(False)
        S = theme.SPACE

        self._logo = tk.Label(self, anchor="w", padx=S["lg"], pady=S["lg"],
                              cursor="arrow")
        self._logo.pack(fill="x")
        self._word = tk.Frame(self)
        self._word_a = tk.Label(self._word, text="MCARS",
                                font=theme.font("display", "bold"))
        self._word_b = tk.Label(self._word, text="PH.",
                                font=theme.font("display", "bold"))
        self._word_a.pack(side="left")
        self._word_b.pack(side="left")

        self._nav = tk.Frame(self)
        self._nav.pack(fill="both", expand=True, pady=(S["sm"], 0))

        self._collapse = self._make_item(self, "collapse", "Collapse",
                                         "\uE76B", "\u2039")
        self._collapse.pack(side="bottom", fill="x", pady=(0, S["sm"]))
        self._collapse.bind("<Button-1>", lambda e: self.toggle(), add="+")
        for w in self._collapse.winfo_children():
            w.bind("<Button-1>", lambda e: self.toggle(), add="+")

        self.apply_theme(theme.get())

    # ── Public API ────────────────────────────────────────────

    @staticmethod
    def glyph_font():
        try:
            families = set(tkfont.families())
        except Exception:
            return None
        for face in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
            if face in families:
                return (face, theme.TYPE["title"])
        return None

    @property
    def active(self):
        return self._active

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_on_select(self, cb):
        self._on_select = cb

    def set_on_collapse(self, cb):
        self._on_collapse = cb

    def add_item(self, key: str, label: str, glyph: str, fallback: str):
        item = self._make_item(self._nav, key, label, glyph, fallback)
        item.pack(fill="x", padx=theme.SPACE["sm"], pady=1)
        self._items[key] = item
        for w in (item, *item.winfo_children()):
            w.bind("<Button-1>", lambda e, k=key: self._select(k), add="+")
        self._paint_item(key)

    def set_active(self, key: str):
        self._active = key
        for k in self._items:
            self._paint_item(k)

    def set_collapsed(self, collapsed: bool, animate: bool = True):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        target = self._collapsed_w if collapsed else self._expanded
        start = self.winfo_width() if self.winfo_width() > 1 else self.cget("width")
        self._parts["collapse"]["glyph"].configure(
            text=self._glyph("\uE76C" if collapsed else "\uE76B",
                             "\u203a" if collapsed else "\u2039"))
        self._parts["collapse"]["label"].configure(
            text="Expand" if collapsed else "Collapse")

        def step(t):
            w = int(round(start + (target - start) * t))
            self.configure(width=w)
            self._show_labels(w >= self._px(LABEL_MIN_WIDTH))

        def done():
            self.configure(width=target)
            self._show_labels(not collapsed)
            self._reload_logo()
            if self._on_collapse:
                self._on_collapse(collapsed)

        effects.tween(self, theme.MOTION["sidebar"] if animate else 0,
                      step, done=done, key="width")

    def toggle(self):
        self.set_collapsed(not self._collapsed)

    def apply_theme(self, colors: dict):
        c = colors
        self.configure(bg=c["sidebar_bg"],
                       highlightthickness=1,
                       highlightbackground=c["sidebar_border"],
                       highlightcolor=c["sidebar_border"])
        for w in (self._logo, self._word, self._nav):
            w.configure(bg=c["sidebar_bg"])
        self._word_a.configure(bg=c["sidebar_bg"], fg=c["sidebar_active_fg"])
        self._word_b.configure(bg=c["sidebar_bg"], fg=c["brand"])
        for k in list(self._items) + ["collapse"]:
            self._paint_item(k)
        self._reload_logo()

    # ── Items ─────────────────────────────────────────────────

    def _glyph(self, glyph: str, fallback: str) -> str:
        return glyph if self._glyph_font else fallback

    def _make_item(self, parent, key, label, glyph, fallback) -> tk.Frame:
        S = theme.SPACE
        item = tk.Frame(parent, cursor="hand2")
        bar = tk.Frame(item, width=3)
        bar.pack(side="left", fill="y")
        g = tk.Label(item, text=self._glyph(glyph, fallback), width=2,
                     font=self._glyph_font or theme.font("title"),
                     cursor="hand2", padx=S["sm"], pady=S["sm"])
        g.pack(side="left")
        lb = tk.Label(item, text=label, anchor="w", cursor="hand2",
                      font=theme.font("body"), padx=S["xs"], pady=S["sm"])
        lb.pack(side="left", fill="x", expand=True)
        self._parts[key] = {"frame": item, "bar": bar, "glyph": g,
                            "label": lb, "hover": False, "text": label}
        for w in (item, bar, g, lb):
            w.bind("<Enter>", lambda e, k=key: self._hover(k, True), add="+")
            w.bind("<Leave>", lambda e, k=key: self._hover(k, False), add="+")
        return item

    def _paint_item(self, key):
        p = self._parts.get(key)
        if not p:
            return
        c = theme.get()
        active = key == self._active
        if active:
            bg, fg, bar = c["sidebar_active_bg"], c["sidebar_active_fg"], c["brand"]
        elif p["hover"]:
            bg, fg, bar = c["sidebar_hover_bg"], c["sidebar_active_fg"], c["sidebar_hover_bg"]
        else:
            bg, fg, bar = c["sidebar_bg"], c["sidebar_fg"], c["sidebar_bg"]
        p["frame"].configure(bg=bg)
        p["bar"].configure(bg=bar)
        p["glyph"].configure(bg=bg, fg=fg)
        p["label"].configure(bg=bg, fg=fg,
                             font=theme.font("body", "bold" if active else "normal"))

    def _hover(self, key, on):
        p = self._parts[key]
        p["hover"] = on
        self._paint_item(key)
        if self._collapsed and key != "collapse":
            self._tooltip(p["frame"], p["text"] if on else None)

    def _select(self, key):
        self.set_active(key)
        if self._on_select:
            self._on_select(key)

    def _show_labels(self, show: bool):
        for p in self._parts.values():
            if show and not p["label"].winfo_ismapped():
                p["label"].pack(side="left", fill="x", expand=True)
            elif not show and p["label"].winfo_ismapped():
                p["label"].pack_forget()

    # ── Tooltip (collapsed mode) ──────────────────────────────

    def _tooltip(self, anchor, text):
        if self._tip_after:
            self.after_cancel(self._tip_after)
            self._tip_after = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
        if not text:
            return

        def show():
            c = theme.get()
            tip = tk.Toplevel(self)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            tk.Label(tip, text=text, bg=c["heading"], fg=c["bg"],
                     font=theme.font("small"), padx=theme.SPACE["sm"],
                     pady=theme.SPACE["xs"]).pack()
            x = anchor.winfo_rootx() + anchor.winfo_width() + self._px(6)
            y = anchor.winfo_rooty() + anchor.winfo_height() // 2 - self._px(10)
            tip.geometry(f"+{x}+{y}")
            self._tip = tip

        self._tip_after = self.after(400, show)

    # ── Logo ──────────────────────────────────────────────────

    def _reload_logo(self):
        """Show the mode's PNG scaled to the sidebar width, else the wordmark."""
        c = theme.get()
        width = (self.cget("width") if not self._collapsed else 0)
        inner = int(width) - 2 * theme.SPACE["lg"]
        if self._collapsed or inner < 60:
            self._logo.configure(image="", text="", bg=c["sidebar_bg"])
            self._logo.pack_forget()
            self._word.pack_forget()
            self._logo.pack(fill="x", before=self._nav)
            return
        path = ASSETS / LOGO_FILES[theme.current]
        img = self._logo_cache.get((theme.current, inner))
        if img is None and path.exists():
            try:
                from PIL import Image, ImageTk
                src = Image.open(path).convert("RGBA")
                h = max(1, int(src.height * inner / src.width))
                src = src.resize((inner, h), Image.LANCZOS)
                img = ImageTk.PhotoImage(src)
                self._logo_cache[(theme.current, inner)] = img
            except Exception:
                img = None
        self._word.pack_forget()
        if img is not None:
            self._logo_img = img
            self._logo.configure(image=img, text="", bg=c["sidebar_bg"])
            self._logo.pack(fill="x", before=self._nav)
        else:
            self._logo.pack_forget()
            self._word.pack(fill="x", padx=theme.SPACE["lg"],
                            pady=theme.SPACE["lg"], before=self._nav)
```

- [ ] **Step 5: Run `python verify.py`** — expect `ALL PROOFS PASS`.

- [ ] **Step 6: Commit**

```bash
git add src/ui/sidebar.py src/ui/assets/README.md verify.py
git commit -m "feat: sidebar widget with logo, nav items, collapse tween and tooltips"
```

---

## Task 4: Shell rebuild in `MainWindow` (sidebar, header, pages, motion)

**Files:**
- Modify: `src/ui/main_window.py` — replace `SECTIONS`, `_build_ui` (lines 284-404), `_show_section`, `_set_drawer`, `_toggle_drawer`, `_init_rail`, `_save_rail_width` (405-472), `_toggle_theme` (262-269), `_retheme_tabs` (271-280); extend `_apply_theme` with new styles
- Create: `scripts/screenshot_ui.py`
- Modify: `verify.py` (extend the smoke test)

**Interfaces:**
- Consumes: `Sidebar` (Task 3), `effects.slide_in / animate_press / tween` (Task 2), `theme.MOTION` (Task 1)
- Produces on `MainWindow`:
  - `PAGES = (("dashboard", "Dashboard", "\uE80F", "\u25a3"), ("accounts", "Accounts", "\uE716", "\u25c9"), ("queue", "Queue", "\uE8FD", "\u2261"), ("compose", "Compose", "\uE70F", "\u270e"), ("monitor", "Monitor", "\uE9D9", "\u25d4"), ("log", "Log", "\uE7C3", "\u25a4"))`
  - `self.sidebar: Sidebar`, `self._pages: dict[str, tk.Widget]`, `self._page: str`
  - `_show_page(key: str, animate: bool = True)`
  - `self.dashboard_page` (placeholder frame in this task; real page in Task 8)
  - `self._header_title: ttk.Label`, `self._header_chip: ttk.Label`, `set_selection_chip(text: str)`
  - ttk styles `Header.TFrame`, `PageTitle.TLabel`, `Chip.TLabel`, `Content.TFrame`
  - keeps `profiles_tab`, `queue_tab`, `share_tab`, `memory_tab`, `log_tab`, `theme_btn`, `logout_btn`, `_set_activity`, `_set_progress`, `_update_status_counts`, `_poll_queue`, `_handle_result`

- [ ] **Step 1: Extend the smoke test in `verify.py`**

Inside the existing `step("tkinter smoke test")` block, after the `set_on_*` loop and before `app.update_idletasks()`:

```python
    _fx.set_animations_override(False)
    for key, *_ in MainWindow.PAGES:
        if key not in app._pages:
            failures.append(f"page {key!r} not registered")
        app._show_page(key, animate=False)
        app.update_idletasks()
        if app.sidebar.active != key:
            failures.append(f"sidebar not active on {key!r}")
    app.sidebar.set_collapsed(True, animate=False)
    app.sidebar.set_collapsed(False, animate=False)
    app._toggle_theme(); app.update(); app._toggle_theme(); app.update()
    if float(app.attributes("-alpha")) != 1.0:
        failures.append("window alpha not restored after theme toggle")
    for attr in ("dashboard_page", "sidebar", "_header_title"):
        if getattr(app, attr, None) is None:
            failures.append(f"MainWindow.{attr} missing")
    _fx.set_animations_override(None)
```

Note: `_toggle_theme` persists `ui_theme`; the two toggles restore the saved value.

- [ ] **Step 2: Run `python verify.py`** — expect `AttributeError: type object 'MainWindow' has no attribute 'PAGES'` as a failure.

- [ ] **Step 3: Rewrite the shell**

At the top of `main_window.py` add `from src.ui.sidebar import Sidebar` next to the other `src.ui` imports and `import tkinter as tk` if absent. Replace the `SECTIONS` constant, `_build_ui`, and the "Shell behaviour" methods (`_show_section`, `_set_drawer`, `_toggle_drawer`, `_init_rail`, `_save_rail_width`) with:

```python
    PAGES = (("dashboard", "Dashboard", "\uE80F", "\u25a3"),
             ("accounts", "Accounts", "\uE716", "\u25c9"),
             ("queue", "Queue", "\uE8FD", "\u2261"),
             ("compose", "Compose", "\uE70F", "\u270e"),
             ("monitor", "Monitor", "\uE9D9", "\u25d4"),
             ("log", "Log", "\uE7C3", "\u25a4"))

    def _build_ui(self):
        S = theme.SPACE
        px = self.px
        from src.storage import config_manager as cfg

        # ── Status bar (bottom, packed first so it always owns the strip) ──
        statusbar = ttk.Frame(self, style="StatusBar.TFrame")
        statusbar.pack(side="bottom", fill="x")
        self._sb_left = ttk.Label(statusbar, text="Ready",
                                  style="StatusBar.TLabel")
        self._sb_left.pack(side="left", padx=S["lg"], pady=S["xs"] - 1)
        self._sb_right = ttk.Label(statusbar, text="",
                                   style="StatusBar.TLabel")
        self._sb_right.pack(side="right", padx=S["lg"], pady=S["xs"] - 1)
        self._sb_progress = ttk.Progressbar(
            statusbar, style="StatusBar.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", length=px(160))
        self._sb_progress_text = ttk.Label(statusbar, text="",
                                           style="StatusBar.TLabel")
        self._progress_shown = False
        self._progress_value = 0.0
        self._ram_text = ""
        self._selection_text = ""

        # ── Body: sidebar | (header / content) ────────────────────────────
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        self.sidebar = Sidebar(body, px=self.px)
        self.sidebar.pack(side="left", fill="y")
        for key, label, glyph, fallback in self.PAGES:
            self.sidebar.add_item(key, label, glyph, fallback)
        self.sidebar.set_on_select(self._show_page)
        self.sidebar.set_on_collapse(
            lambda c: cfg.save_setting("ui_sidebar_collapsed", "1" if c else "0"))
        self.sidebar.set_collapsed(
            cfg.get_setting("ui_sidebar_collapsed", "0") == "1", animate=False)

        main = ttk.Frame(body, style="Content.TFrame")
        main.pack(side="left", fill="both", expand=True)

        header = ttk.Frame(main, style="Header.TFrame")
        header.pack(side="top", fill="x")
        self._header_title = ttk.Label(header, text="", style="PageTitle.TLabel")
        self._header_title.pack(side="left", padx=S["xl"], pady=S["md"])
        self._header_chip = ttk.Label(header, text="", style="Chip.TLabel")
        self.theme_btn = ttk.Button(
            header, text="Dark" if theme.current == "light" else "Light",
            command=self._toggle_theme, style="Header.TButton")
        self.theme_btn.pack(side="right", padx=(0, S["xl"]))
        self.logout_btn = ttk.Button(header, text="Log Out",
                                     command=self._on_logout,
                                     style="Header.TButton")
        self.logout_btn.pack(side="right", padx=(0, S["md"]))
        effects.animate_press(self.theme_btn)
        effects.animate_press(self.logout_btn)

        content = ttk.Frame(main, style="Content.TFrame")
        content.pack(fill="both", expand=True, padx=(S["md"], S["md"]),
                     pady=(0, S["sm"]))
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        # ── Pages ─────────────────────────────────────────────────────────
        self.dashboard_page = ttk.Frame(content)       # real page: Task 8
        ttk.Label(self.dashboard_page, text="Dashboard",
                  style="SectionTitle.TLabel").pack(anchor="w",
                                                    padx=S["lg"], pady=S["lg"])
        accounts_host = ScrollFrame(content)            # AccountsPage: Task 10
        self.profiles_tab = ProfilesTab(accounts_host.interior)
        self.profiles_tab.pack(fill="both", expand=True)
        self.queue_tab = QueueTab(content)
        self.share_tab = ShareTab(content)
        self.memory_tab = MemoryMonitorTab(content, manager=self.manager)
        self.log_tab = LogTab(content)
        self._pages = {"dashboard": self.dashboard_page,
                       "accounts": accounts_host,
                       "queue": self.queue_tab,
                       "compose": self.share_tab,
                       "monitor": self.memory_tab,
                       "log": self.log_tab}
        for frame in self._pages.values():
            frame.grid(row=0, column=0, sticky="nsew")
        self._page = None
        self._show_page(cfg.get_setting("ui_page", "dashboard"), animate=False)

        effects.install_wheel_router(self)
        self.after(200, self._load_saved_groups)
        self._connect_callbacks()
        self.memory_tab.set_on_stats(self._on_memory_stats)
        self._retheme_tabs()

    # ── Shell behaviour ───────────────────────────────────────

    def _show_page(self, key: str, animate: bool = True):
        if key not in self._pages:
            key = "dashboard"
        previous = self._page
        self._page = key
        self.sidebar.set_active(key)
        title = next(t for k, t, *_ in self.PAGES if k == key)
        self._header_title.configure(text=title)
        self._update_selection_chip()
        frame = self._pages[key]
        if animate and previous is not None and previous != key:
            effects.slide_in(frame, dx=self.px(24),
                             duration_ms=theme.MOTION["page"])
        else:
            frame.tkraise()
        from src.storage import config_manager as cfg
        cfg.save_setting("ui_page", key)
        # Per-page refresh, as the tab-change handler used to do.
        try:
            if key == "queue":
                self.queue_tab.refresh_profiles()
            elif key == "monitor":
                self.memory_tab._refresh_now()
            elif key == "accounts":
                refresh = getattr(self.profiles_tab, "refresh_accounts", None)
                if refresh:
                    refresh()
            elif key == "dashboard":
                refresh = getattr(self.dashboard_page, "refresh", None)
                if refresh:
                    refresh()
        except Exception:
            pass

    def set_selection_chip(self, text: str):
        """Header chip: the scope Queue and Compose act on."""
        self._selection_text = text
        self._update_selection_chip()

    def _update_selection_chip(self):
        show = self._page in ("queue", "compose") and self._selection_text
        if show:
            self._header_chip.configure(text=self._selection_text)
            if not self._header_chip.winfo_ismapped():
                self._header_chip.pack(side="left", padx=(0, theme.SPACE["md"]))
        elif self._header_chip.winfo_ismapped():
            self._header_chip.pack_forget()
```

Replace `_toggle_theme` and `_retheme_tabs`:

```python
    def _toggle_theme(self):
        """Dip the window, swap the palette at the bottom, come back up.

        Tk cannot crossfade widgets, so the whole window's alpha dips to
        0.35 (80 ms), the theme is applied while dim, then alpha returns
        (140 ms). With animations off the swap is instant.
        """
        if getattr(self, "_theme_busy", False):
            return
        self._theme_busy = True
        out_ms, in_ms = 80, theme.MOTION["theme"] - 80

        def swap():
            mode = theme.toggle()
            from src.storage import config_manager as cfg
            cfg.save_setting("ui_theme", mode)
            self._apply_theme()
            self.theme_btn.config(text="Dark" if mode == "light" else "Light")
            self._retheme_tabs()
            self.update_idletasks()

        def come_back():
            effects.tween(self, in_ms,
                          lambda t: self.attributes("-alpha", 0.35 + 0.65 * t),
                          done=lambda: (self.attributes("-alpha", 1.0),
                                        setattr(self, "_theme_busy", False)),
                          key="theme")

        effects.tween(self, out_ms,
                      lambda t: self.attributes("-alpha", 1.0 - 0.65 * t),
                      done=lambda: (swap(), come_back()),
                      easing=effects.linear, key="theme")

    def _retheme_tabs(self):
        """Push the active palette into raw-tk widgets in every page."""
        for tab in (self.profiles_tab, self.queue_tab, self.share_tab,
                    self.memory_tab, self.log_tab, self.sidebar,
                    self.dashboard_page, self._pages.get("accounts")):
            apply_theme = getattr(tab, "apply_theme", None)
            if callable(apply_theme):
                try:
                    apply_theme(theme.get())
                except Exception:
                    pass
```

In `_apply_theme`, after the `TopBar.TFrame` / `Wordmark.TLabel` lines (keep them; other code may reference them), add:

```python
        style.configure("Header.TFrame", background=c["header_bg"])
        style.configure("Content.TFrame", background=c["bg"])
        style.configure("PageTitle.TLabel", background=c["header_bg"],
                        foreground=c["heading"],
                        font=theme.font("display", "bold"))
        style.configure("Chip.TLabel", background=c["chip_bg"],
                        foreground=c["chip_fg"], font=theme.font("small", "bold"),
                        padding=(theme.SPACE["sm"], 2))
```

and change `Header.TButton`'s `background=c["toolbar_bg"]` to `background=c["header_bg"]`.

In `_update_status_counts`, extend the right-hand text so it ends with `Selected: {self._selection_text or 'all'}` only when `self._selection_text` is non-empty:

```python
        if self._selection_text:
            text += f"   \u2022   {self._selection_text}"
```

(place this after the RAM segment is appended, before the change-check).

Delete the now-unused `_set_drawer`, `_toggle_drawer`, `_init_rail`, `_save_rail_width`, `_show_section`, and the `SECTIONS` tuple. Search the file for `_rail`, `_drawer`, `_nav_buttons`, `self.body` and remove every remaining reference (`destroy()` may touch none; `_toggle_theme` no longer calls `_show_section`).

- [ ] **Step 4: Create `scripts/screenshot_ui.py`**

```python
"""Screenshot every page of the app in both themes, two sizes, sidebar
expanded and collapsed. Output: ~/.autoshare/screenshots/<name>.png.

Run from the project root:  python scripts/screenshot_ui.py
No browser is launched and nothing is written to the sheet: the
DriverManager thread is never started.
"""
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ui import theme, effects
theme.enable_dpi_awareness()
from PIL import ImageGrab
from src.core.driver_manager import DriverManager
from src.ui.main_window import MainWindow

OUT = pathlib.Path.home() / ".autoshare" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
SIZES = {"min": (1100, 700), "hd": (1920, 1080)}


def main() -> int:
    effects.set_animations_override(False)
    manager = DriverManager()
    app = MainWindow(driver_manager=manager)
    manager.log = app.log_tab.write
    app.lift()
    app.attributes("-topmost", True)
    saved_mode = theme.current

    def grab(name):
        app.deiconify()
        for _ in range(8):
            app.update_idletasks(); app.update(); time.sleep(0.06)
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        img = ImageGrab.grab(all_screens=True)
        box = (max(0, x), max(0, y - 32), min(img.width, x + w),
               min(img.height, y + h))
        if box[2] > box[0] and box[3] > box[1]:
            img.crop(box).save(OUT / f"{name}.png")
            print("saved", name)

    for size, (W, H) in SIZES.items():
        app.geometry(f"{app.px(W)}x{app.px(H)}+0+0")
        for mode in ("light", "dark"):
            if theme.current != mode:
                app._toggle_theme(); app.update()
            for collapsed in (False, True):
                app.sidebar.set_collapsed(collapsed, animate=False)
                for key, *_ in MainWindow.PAGES:
                    app._show_page(key, animate=False)
                    grab(f"{size}_{mode}_{'c' if collapsed else 'e'}_{key}")
    if theme.current != saved_mode:
        app._toggle_theme(); app.update()
    app.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run `python verify.py`** — expect `ALL PROOFS PASS`. Then run `python scripts/screenshot_ui.py` and open `~/.autoshare/screenshots/min_light_e_queue.png`, `min_dark_c_compose.png`, `hd_light_e_dashboard.png`: sidebar on the left with the wordmark (no PNG yet), page title in the header, no clipped controls, status bar intact.

- [ ] **Step 6: Commit**

```bash
git add src/ui/main_window.py scripts/screenshot_ui.py verify.py
git commit -m "feat: admin shell with sidebar, page header, page slide and theme dip"
```

---

## Task 5: Press animation on every primary button

**Files:**
- Modify: `src/ui/queue_tab.py`, `src/ui/share_tab.py`, `src/ui/profiles_tab.py`, `src/ui/memory_monitor.py`, `src/ui/log_tab.py` — one line per `ttk.Button(... style="Accent.TButton" ...)` and `Timeline.TButton`

**Interfaces:**
- Consumes: `effects.animate_press(button)` (Task 2)

- [ ] **Step 1: Proof** — append to `verify.py` inside the smoke test after `_retheme_tabs` checks:

```python
    import tkinter.ttk as _ttk
    _accent = [w for w in app.winfo_children()]  # placeholder list, replaced below
    def _walk(w):
        yield w
        for ch in w.winfo_children():
            yield from _walk(ch)
    _unbound = [w for w in _walk(app)
                if isinstance(w, _ttk.Button)
                and str(w.cget("style")) in ("Accent.TButton", "Timeline.TButton")
                and "ButtonRelease-1" not in " ".join(w.bind())]
    if _unbound:
        failures.append(f"{len(_unbound)} accent buttons without animate_press")
```

- [ ] **Step 2: Run `python verify.py`** — expect `FAIL: N accent buttons without animate_press`.

- [ ] **Step 3: Bind them**

In each tab file, `from src.ui import effects` (already imported in most), and after each `ttk.Button(...)` creation whose style is `Accent.TButton` or `Timeline.TButton`, add `effects.animate_press(<button>)`. Sites: `queue_tab.py:135-138, 175-178, 301-306, 374-378, 417-420, 432-435`; `share_tab.py:123-127, 129-132, 196-199` and the `Post` button in `_open_compose_dialog` (~line 630); `profiles_tab.py:63-65, 79-82, 122-126, 129-133, 136-140`. Buttons created without an attribute: wrap as `effects.animate_press(ttk.Button(...))` then `.pack(...)` on the returned widget.

- [ ] **Step 4: Run `python verify.py`** — `ALL PROOFS PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/ui/queue_tab.py src/ui/share_tab.py src/ui/profiles_tab.py verify.py
git commit -m "feat: press pulse on every accent button"
```

---

## Task 6: Mirror the sheet's STATUS column into the database

**Files:**
- Modify: `src/storage/roster_sheet.py:31-38` (HEADERS), `:140-155` (`_poll_once`)
- Modify: `src/storage/database.py:76-90` (CREATE TABLE), `:138-165` (`_migrate`), `:420-476` (`upsert_account`, `list_accounts`), append `pending_accounts`, `count_pending`
- Modify: `verify.py`

**Interfaces:**
- Produces:
  - `roster_sheet.HEADERS["STATUS"] == "sheet_status"`; `parse_accounts` dicts carry `sheet_status` (stripped cell text, `""` when absent)
  - `SheetWatcher.last_ok: float` — `time.time()` of the last successful poll, `0.0` before
  - `db.upsert_account(..., sheet_status: str = "")`
  - `db.list_accounts()` dicts include `sheet_status`
  - `db.pending_accounts() -> list[dict]` — `sheet_status == ''` and `status != 'disabled'`, roster order
  - `db.count_pending() -> tuple[int, int]` — `(pending, pending_without_profile)`

- [ ] **Step 1: Proof**

```python
step("sheet_status mirror")
from src.storage import roster_sheet as _rs, database as _db
_rows = [["NO", "FACEBOOK NAME", "USERNAME", "PASSWORD", "STATUS"],
         ["1", "A", "verify_a@example.com", "x", "LOGGED IN"],
         ["2", "B", "verify_b@example.com", "x", ""],
         ["3", "C", "verify_c@example.com", "x"]]
_parsed = _rs.parse_accounts(_rows)
if [a.get("sheet_status") for a in _parsed] != ["LOGGED IN", "", ""]:
    failures.append(f"parse_accounts sheet_status: {[a.get('sheet_status') for a in _parsed]}")
_have = {r[1] for r in _db._get_conn().execute("PRAGMA table_info(accounts)")}
if "sheet_status" not in _have:
    failures.append("accounts.sheet_status column missing")
for _a in _parsed:
    _db.upsert_account(**_a)
_pend = [a["username"] for a in _db.pending_accounts()
         if a["username"].startswith("verify_")]
if _pend != ["verify_b@example.com", "verify_c@example.com"]:
    failures.append(f"pending_accounts: {_pend}")
_n, _np = _db.count_pending()
if _n < 2 or _np < 2:
    failures.append(f"count_pending: {(_n, _np)}")
_db._get_conn().execute("DELETE FROM accounts WHERE username LIKE 'verify_%@example.com'")
_db._get_conn().commit()
if not hasattr(_rs.SheetWatcher(interval=999), "last_ok"):
    failures.append("SheetWatcher.last_ok missing")
print("ok" if not [f for f in failures if "sheet_status" in f or "pending" in f or "last_ok" in f] else "FAILED")
```

- [ ] **Step 2: Run** — expect `parse_accounts sheet_status: [None, None, None]` etc.

- [ ] **Step 3: Implement**

`roster_sheet.py` — HEADERS:

```python
HEADERS: dict[str, str] = {
    "FACEBOOK NAME": "facebook_name",
    "USERNAME": "username",
    "PASSWORD": "password",
    "GMAIL": "gmail",
    "PASS FOR GMAIL": "gmail_password",
    "NUMBER": "number",
    # Read-only mirror of the cell the login runs write. "" means the row
    # has never been given a verdict - the "pending" set the dashboard counts.
    "STATUS": "sheet_status",
}
```

Update the module docstring line that lists the mapped headers to include `STATUS -> sheet_status (mirror only)`. In `SheetWatcher.__init__` add `self.last_ok: float = 0.0`; in `_poll_once` set `self.last_ok = time.time()` right after `self._last_error = None` (add `import time`).

`database.py` — in the `CREATE TABLE IF NOT EXISTS accounts` block add after `status_reason`:

```sql
            sheet_status    TEXT    NOT NULL DEFAULT '',
```

and extend the comment above it: `sheet_status mirrors the sheet's STATUS cell (sheet-owned, written only by the sync).` In `_migrate`, add `"sheet_status"` to the tuple in the `for col in (...)` loop.

`upsert_account` signature: add `sheet_status: str = ""` after `gmail_password`; UPDATE sets `sheet_status = ?` (add the parameter after `number`), INSERT includes the column and value. `list_accounts` SELECT adds `, sheet_status` after `status_reason`.

Append after `count_disabled`:

```python
def pending_accounts() -> list[dict]:
    """Roster rows whose sheet STATUS cell is blank and that are not disabled.

    These are the accounts nobody has ever logged in from this tool - the set
    the dashboard's "Log in pending" button targets.
    """
    conn = _get_conn()
    sql = ("SELECT sheet_no, facebook_name, username, gmail, number, "
           "linked_profile, status, status_reason, sheet_status FROM accounts "
           "WHERE sheet_status = '' AND status != 'disabled' "
           "ORDER BY CASE WHEN sheet_no IS NULL THEN 1 ELSE 0 END, sheet_no")
    return [dict(r) for r in conn.execute(sql)]


def count_pending() -> tuple[int, int]:
    """(pending accounts, pending accounts with no linked Brave profile)."""
    conn = _get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM accounts "
        "WHERE sheet_status = '' AND status != 'disabled'").fetchone()[0]
    unlinked = conn.execute(
        "SELECT COUNT(*) FROM accounts WHERE sheet_status = '' "
        "AND status != 'disabled' AND linked_profile = ''").fetchone()[0]
    return total, unlinked
```

- [ ] **Step 4: Run `python verify.py`** — `ALL PROOFS PASS`. Then `python scripts/import_accounts.py --dry-run` still parses the live sheet without error.

- [ ] **Step 5: Commit**

```bash
git add src/storage/roster_sheet.py src/storage/database.py verify.py
git commit -m "feat: mirror the sheet STATUS column so pending accounts are countable"
```

---

## Task 7: `SheetWriter` and the `login_accounts` command

**Files:**
- Modify: `src/storage/sheet_status.py` (append `SheetWriter`)
- Modify: `src/core/driver_manager.py` — public helper after `check_login_status` (~line 235), dispatcher branch (after the `check_login_status` branch in `_async_run`), new `_do_login_accounts` after `_do_check_login_status` (~line 1897), `_relogin_profile` log line
- Modify: `src/ui/main_window.py` — two new branches in `_handle_result`
- Modify: `verify.py`

**Interfaces:**
- Consumes: `db.list_accounts`, `db.account_for_profile`, `DriverManager._relogin_profile(profile_name) -> bool`, `_record_and_publish`
- Produces:
  - `sheet_status.SheetWriter(sheet_id=..., tab=..., key_path=...)` with `.on: bool`, `.error: str`, `.write(username, text) -> bool`, `.mark_in_progress(username) -> bool`
  - `DriverManager.login_accounts(usernames: list[str])`
  - result dicts `{"type": "login_accounts_progress", "current", "total", "username", "profile_name", "ok", "message"}` and `{"type": "login_accounts_result", "ok", "error"?, "total", "logged_in": [(username, reason)], "failed": [...], "skipped": [...]}`
  - `DriverManager._brave_running() -> bool` (static)
  - `MainWindow` handles both types; after a result calls `self.profiles_tab.set_login_enabled(True)` and `self.dashboard_page.set_login_running(False)` when those methods exist (they arrive in Tasks 8 and 10)

- [ ] **Step 1: Proof**

```python
step("login_accounts command")
import asyncio as _aio, queue as _q
from src.core.driver_manager import DriverManager as _DM
_m = _DM()
_m.login_accounts(["a@example.com"])
_cmd = _m.cmd_queue.get_nowait()
if _cmd != {"type": "login_accounts", "usernames": ["a@example.com"]}:
    failures.append(f"login_accounts enqueued {_cmd}")
# Drive the handler with a stubbed re-login and stubbed preflight.
_calls = []
async def _fake_relogin(profile_name):
    _calls.append(profile_name); return profile_name == "P-ok"
_m._relogin_profile = _fake_relogin
_m._brave_running = staticmethod(lambda: False)
_m._watch_autos = {}
from src.storage import database as _db
_db.upsert_account(1, "OK", "verify_ok@example.com", password="x")
_db.link_account("verify_ok@example.com", "P-ok")
_db.upsert_account(2, "NOPROF", "verify_np@example.com", password="x")
import src.storage.sheet_status as _ss
class _NoWriter:
    on = False
    def mark_in_progress(self, u): return False
_ss.SheetWriter = lambda *a, **k: _NoWriter()
_aio.run(_m._do_login_accounts({"type": "login_accounts",
                                 "usernames": ["verify_ok@example.com",
                                               "verify_np@example.com",
                                               "ghost@example.com"]}))
_out = []
while True:
    try: _out.append(_m.result_queue.get_nowait())
    except _q.Empty: break
_types = [r["type"] for r in _out]
_res = _out[-1]
if _types.count("login_accounts_progress") != 3 or _types[-1] != "login_accounts_result":
    failures.append(f"login_accounts events: {_types}")
if _calls != ["P-ok"]:
    failures.append(f"relogin called for {_calls}")
if [u for u, _ in _res.get("logged_in", [])] != ["verify_ok@example.com"]:
    failures.append(f"logged_in {_res.get('logged_in')}")
if sorted(u for u, _ in _res.get("skipped", [])) != ["ghost@example.com", "verify_np@example.com"]:
    failures.append(f"skipped {_res.get('skipped')}")
_db._get_conn().execute("DELETE FROM accounts WHERE username LIKE 'verify_%@example.com'")
_db._get_conn().commit()
print("ok" if not [f for f in failures if "login_accounts" in f or "relogin" in f or "logged_in" in f or "skipped" in f] else "FAILED")
```

Note: `_do_login_accounts` sleeps between accounts; make the sleep `await asyncio.sleep(0)` when `self._fast_tests` is true — set `_m._fast_tests = True` in the proof after constructing `_m`.

- [ ] **Step 2: Run** — expect `AttributeError: 'DriverManager' object has no attribute 'login_accounts'`.

- [ ] **Step 3: `SheetWriter`** — append to `sheet_status.py`:

```python
class SheetWriter:
    """Resolve the sheet once, then write many STATUS cells.

    push_account_status() re-reads the header and the username column on
    every call - fine for one verdict at the end of a watch, five HTTP calls
    too many when a run writes LOGGING IN before each of forty accounts.
    Construction does the network work, so build it off the event loop.
    Every failure is swallowed into .on/.error: the sheet is a mirror, never
    a reason to stop logging accounts in.
    """

    def __init__(self, sheet_id: str = api.DEFAULT_SHEET_ID,
                 tab: str = api.DEFAULT_TAB,
                 key_path: Path | str = api.DEFAULT_KEY):
        self.on = False
        self.error = ""
        self._key_path = key_path
        self._sheet_id = sheet_id
        self._tab = tab
        try:
            if not Path(key_path).exists():
                raise FileNotFoundError(f"no service-account key at {key_path}")
            self._tok = api.token(key_path)
            self._gid = resolve_gid(self._tok, sheet_id, tab)
            if self._gid is None:
                raise ValueError(f"tab {tab!r} not found")
            cols = resolve_columns(self._tok, sheet_id, tab)
            self._status_col = cols["status"]
            self._rows = build_row_index(self._tok, sheet_id, tab, cols["username"])
            self.on = True
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"[:200]

    def write(self, username: str, text: str) -> bool:
        row = self._rows.get((username or "").strip().lower()) if self.on else None
        if not row:
            return False
        for attempt in range(2):
            try:
                write_status(self._tok, self._sheet_id, self._gid, self._tab,
                             row, text, self._status_col)
                return True
            except Exception as e:
                if attempt == 0:
                    try:
                        self._tok = api.token(self._key_path)
                        continue
                    except Exception:
                        pass
                self.error = f"{type(e).__name__}: {e}"[:200]
        return False

    def mark_in_progress(self, username: str) -> bool:
        return self.write(username, IN_PROGRESS)
```

- [ ] **Step 4: DriverManager** — after `check_login_status`:

```python
    def login_accounts(self, usernames: list[str]):
        """Log the given roster accounts in, one at a time, and publish each
        verdict to the sheet. Emits login_accounts_progress / _result."""
        self.cmd_queue.put({"type": "login_accounts",
                            "usernames": list(usernames)})
```

Dispatcher branch, next to `check_login_status`:

```python
                elif cmd_type == "login_accounts":
                    await self._do_login_accounts(cmd)
```

Handler, after `_do_check_login_status`:

```python
    @staticmethod
    def _brave_running() -> bool:
        """Any brave.exe holds Chromium's singleton lock on the shared
        User Data dir, so a login inside a real profile cannot launch."""
        try:
            import psutil
            return any((p.info.get("name") or "").lower() == "brave.exe"
                       for p in psutil.process_iter(["name"]))
        except Exception:
            return False

    async def _do_login_accounts(self, cmd: dict):
        """Log roster accounts in from the GUI.

        Sequential by necessity (Brave's singleton lock), inside each
        account's real profile so the session cookies stay decryptable.
        Per account: LOGGING IN on the sheet, _relogin_profile() (which
        records the verdict and pushes it), a short pause.
        """
        usernames = [u for u in (cmd.get("usernames") or []) if u]
        total = len(usernames)

        def finish(**kw):
            base = {"type": "login_accounts_result", "total": total,
                    "logged_in": [], "failed": [], "skipped": []}
            base.update(kw)
            self.result_queue.put(base)

        if not usernames:
            finish(ok=False, error="No accounts to log in")
            return
        if self._batch_running or self._watch_autos:
            finish(ok=False, error="A run or watch is active - wait for it "
                                   "to finish, then try again")
            return
        if self._brave_running():
            finish(ok=False, error="Brave is open and locks the shared profile "
                                   "directory. Close every Brave window, then "
                                   "try again.")
            return

        from src.storage import sheet_status
        by_user = {a["username"].lower(): a for a in db.list_accounts()}
        writer = await asyncio.to_thread(sheet_status.SheetWriter)
        if not writer.on:
            self.log(f"  \u26a0\ufe0f  live sheet updates off: {writer.error}")
        self.log(f"Logging in {total} account(s)...")
        logged_in, failed, skipped = [], [], []

        for idx, username in enumerate(usernames, 1):
            acct = by_user.get(username.lower())
            profile = (acct or {}).get("linked_profile") or ""
            reason = ""
            ok = False
            if acct is None:
                reason = "not in roster"
                skipped.append((username, reason))
            elif acct.get("status") == "disabled":
                reason = "disabled"
                skipped.append((username, reason))
            elif not profile:
                reason = "no Brave profile - run scripts/provision_profiles.py"
                skipped.append((username, reason))
            else:
                if writer.on:
                    await asyncio.to_thread(writer.mark_in_progress, username)
                ok = await self._relogin_profile(profile, why="Login requested")
                after = db.account_for_profile(profile) or {}
                reason = ("logged in" if ok else
                          (after.get("status_reason") or "could not log in - see log"))
                (logged_in if ok else failed).append((username, reason))
            self.result_queue.put({
                "type": "login_accounts_progress",
                "current": idx, "total": total,
                "username": username, "profile_name": profile, "ok": ok,
                "message": f"[{idx}/{total}] {username}: {reason}",
            })
            if idx < total:
                await asyncio.sleep(0 if getattr(self, "_fast_tests", False)
                                    else random.uniform(2.0, 4.0))

        finish(ok=True, logged_in=logged_in, failed=failed, skipped=skipped)
```

Confirm `random` and `asyncio` are imported at the top of `driver_manager.py` (they are used elsewhere). Change `_relogin_profile`'s signature to `async def _relogin_profile(self, profile_name: str, why: str = "Session expired") -> bool` and its log line to `self.log(f"  \u21bb {why} - logging '{profile_name}' in...")`.

- [ ] **Step 5: MainWindow result handling** — in `_handle_result`, before the final `else`/end of the chain add:

```python
        elif rtype == "login_accounts_progress":
            self.log_tab.write(("\u2713 " if result.get("ok") else "\u2717 ")
                               + result.get("message", ""))
            pname = result.get("profile_name")
            if pname:
                mark = getattr(self.profiles_tab, "mark_login_status", None)
                if mark:
                    mark(pname, bool(result.get("ok")))
                self.queue_tab.update_profile_status(pname, bool(result.get("ok")))
            refresh = getattr(self.dashboard_page, "refresh", None)
            if refresh:
                refresh()

        elif rtype == "login_accounts_result":
            for obj, name in ((self.profiles_tab, "set_login_enabled"),
                              (self.dashboard_page, "set_login_running")):
                fn = getattr(obj, name, None)
                if fn:
                    fn(True if name == "set_login_enabled" else False)
            if not result.get("ok"):
                self.log_tab.write(f"\u2717 Login run refused: {result.get('error')}")
                messagebox.showwarning("Log in accounts", result.get("error", ""),
                                       parent=self)
            else:
                li, fa, sk = (result.get("logged_in", []), result.get("failed", []),
                              result.get("skipped", []))
                self.log_tab.write(f"\n{'=' * 50}")
                self.log_tab.write(f"Login run: {len(li)} logged in, "
                                   f"{len(fa)} failed, {len(sk)} skipped")
                for u, r in fa:
                    self.log_tab.write(f"  \u2717 {u}: {r}")
                for u, r in sk:
                    self.log_tab.write(f"  - {u}: {r}")
                if fa:
                    self.log_tab.write("  Finish checkpoint/2FA accounts with: "
                                       "python scripts/login_accounts.py --only <username>")
                self.log_tab.write(f"{'=' * 50}\n")
            self._set_activity("Ready")
            for obj, name in ((self.profiles_tab, "refresh_accounts"),
                              (self.profiles_tab, "refresh_profiles"),
                              (self.queue_tab, "refresh_profiles"),
                              (self.dashboard_page, "refresh")):
                fn = getattr(obj, name, None)
                if fn:
                    try:
                        fn()
                    except Exception:
                        pass
```

`messagebox` is already imported in `main_window.py` (used by `_on_logout`).

- [ ] **Step 6: Run `python verify.py`** — `ALL PROOFS PASS`.

- [ ] **Step 7: Commit**

```bash
git add src/storage/sheet_status.py src/core/driver_manager.py src/ui/main_window.py verify.py
git commit -m "feat: login_accounts command logs roster accounts in and publishes verdicts"
```

---

## Task 8: Dashboard page

**Files:**
- Create: `src/ui/dashboard_page.py`
- Modify: `src/ui/log_tab.py` (`set_on_alert`)
- Modify: `src/ui/main_window.py` (replace the placeholder; wire hooks; run summary; sync age)
- Modify: `verify.py`

**Interfaces:**
- Consumes: `db.count_accounts`, `db.count_disabled`, `db.logged_in_profiles`, `db.count_pending`, `db.pending_accounts`, `effects.count_up`, `theme.MOTION["count"]`, `DriverManager.login_accounts`
- Produces `class DashboardPage(ttk.Frame)`:
  - `set_on_login_pending(cb)` — `cb(usernames: list[str])`; `set_on_open_log(cb)`
  - `refresh()` — re-read counts, animate numbers, enable/disable the button
  - `set_login_running(running: bool)`
  - `set_run_progress(done: int, total: int, text: str)`; `set_run_summary(text: str)`
  - `set_system(ram: str, procs: int, sessions: int, sync_age: float | None)`
  - `add_alert(stamp: str, text: str)` — thread-safe (marshals via `after`)
  - `apply_theme(colors)`
- `LogTab.set_on_alert(cb)` — `cb(stamp, text)` for every line tagged `error`
- `MainWindow`: `cfg` key `last_run_summary`; `self._sheet_watcher.last_ok` read in `_update_status_counts` every 100 ms, pushed with RAM/procs through `dashboard_page.set_system`

- [ ] **Step 1: Proof**

```python
step("dashboard page")
from src.ui.dashboard_page import DashboardPage as _DP
_root = _tk.Tk(); _root.withdraw(); _fx.set_animations_override(False)
_dp = _DP(_root); _dp.pack()
_got = []
_dp.set_on_login_pending(_got.append)
_dp.refresh(); _root.update_idletasks()
for _name in ("total", "logged_in", "pending", "disabled"):
    if not _dp._stat_labels[_name].cget("text").replace(",", "").isdigit():
        failures.append(f"dashboard stat {_name} not numeric")
_dp.set_run_progress(3, 10, "Rene: sharing"); _dp.set_run_summary("1 ok · 0 failed")
_dp.set_system("7.3/17.9 GB", 17, 6, 12.0); _dp.add_alert("20:11:07", "\u2717 boom")
_root.update()
if "boom" not in _dp._alerts.get("1.0", "end"):
    failures.append("dashboard alert not shown")
_dp._login_btn.invoke()
if _got and not isinstance(_got[0], list):
    failures.append("login pending callback must receive a list")
for _mode in ("light", "dark"):
    _theme.set_mode(_mode); _dp.apply_theme(_theme.get())
_theme.set_mode("light"); _fx.set_animations_override(None); _root.destroy()
print("ok" if not [f for f in failures if "dashboard" in f or "login pending" in f] else "FAILED")
```

Also extend the smoke test: `verify.py` already walks `set_on_*` on the four tabs; add `"dashboard_page"` to that tuple so `set_on_login_pending` / `set_on_open_log` must be wired.

- [ ] **Step 2: Run** — expect `ModuleNotFoundError: src.ui.dashboard_page`.

- [ ] **Step 3: `log_tab.py`** — in `__init__` add `self._on_alert = None`; add

```python
    def set_on_alert(self, callback):
        """callback(stamp, text) for every line tagged error."""
        self._on_alert = callback
```

and in `write`, right after the `tag = "error"` assignment branch (after the if/elif), add:

```python
        if tag == "error" and self._on_alert:
            try:
                self._on_alert(timestamp, stripped)
            except Exception:
                pass
```

- [ ] **Step 4: Create `src/ui/dashboard_page.py`**

```python
"""Landing page: account health, the pending-login button, run activity,
system figures and recent alerts. Reads the database directly for counts;
everything live (progress, RAM, alerts) is pushed in by MainWindow.
"""
import tkinter as tk
from tkinter import ttk

from src.storage import database as db
from src.ui import effects, theme

REFRESH_MS = 5000
MAX_ALERTS = 8


class DashboardPage(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_login_pending = None
        self._on_open_log = None
        self._values = {"total": 0, "logged_in": 0, "pending": 0, "disabled": 0}
        self._stat_labels: dict[str, ttk.Label] = {}
        self._login_running = False
        self._pending_usernames: list[str] = []
        self._alert_lines: list[str] = []
        self._build_ui()
        self.after(REFRESH_MS, self._tick)

    # ── Build ─────────────────────────────────────────────────

    def _build_ui(self):
        S = theme.SPACE
        self.columnconfigure(0, weight=1)

        stats = ttk.Frame(self)
        stats.grid(row=0, column=0, sticky="ew", padx=S["lg"], pady=(S["lg"], S["sm"]))
        for i in range(4):
            stats.columnconfigure(i, weight=1, uniform="stat")
        for i, (key, title, hint) in enumerate((
                ("total", "Total accounts", "roster rows"),
                ("logged_in", "Logged in", "status ok"),
                ("pending", "Need login", "blank STATUS on the sheet"),
                ("disabled", "Disabled", "by Facebook"))):
            card = ttk.Frame(stats, style="Card.TFrame", padding=S["lg"])
            card.grid(row=0, column=i, sticky="nsew",
                      padx=(0 if i == 0 else S["sm"], 0))
            ttk.Label(card, text=title, style="CardMuted.TLabel").pack(anchor="w")
            val = ttk.Label(card, text="0", style="CardValue.TLabel")
            val.pack(anchor="w", pady=(S["xs"], 0))
            ttk.Label(card, text=hint, style="CardMuted.TLabel").pack(anchor="w")
            self._stat_labels[key] = val

        action = ttk.Frame(self)
        action.grid(row=1, column=0, sticky="ew", padx=S["lg"], pady=(0, S["lg"]))
        self._login_btn = effects.animate_press(ttk.Button(
            action, text="Log in 0 pending accounts", style="Accent.TButton",
            command=self._on_login_click, state="disabled"))
        self._login_btn.pack(side="left")
        self._login_hint = ttk.Label(action, text="", style="Muted.TLabel")
        self._login_hint.pack(side="left", padx=S["md"])

        row2 = ttk.Frame(self)
        row2.grid(row=2, column=0, sticky="nsew", padx=S["lg"], pady=(0, S["lg"]))
        self.rowconfigure(2, weight=1)
        for i in range(3):
            row2.columnconfigure(i, weight=1, uniform="row2")
        row2.rowconfigure(0, weight=1)

        run = ttk.Frame(row2, style="Card.TFrame", padding=S["lg"])
        run.grid(row=0, column=0, sticky="nsew")
        ttk.Label(run, text="Run activity", style="CardHeading.TLabel").pack(anchor="w")
        self._run_text = ttk.Label(run, text="Idle", style="CardMuted.TLabel")
        self._run_text.pack(anchor="w", pady=(S["sm"], S["xs"]))
        self._run_bar = ttk.Progressbar(run, orient="horizontal",
                                        mode="determinate", length=200)
        self._run_bar.pack(fill="x")
        self._run_count = ttk.Label(run, text="", style="CardMuted.TLabel")
        self._run_count.pack(anchor="w", pady=(S["xs"], S["sm"]))
        self._run_summary = ttk.Label(run, text="No run yet", style="CardMuted.TLabel")
        self._run_summary.pack(anchor="w")
        effects.bind_wrap(self._run_summary, pad=2 * S["lg"])

        system = ttk.Frame(row2, style="Card.TFrame", padding=S["lg"])
        system.grid(row=0, column=1, sticky="nsew", padx=S["sm"])
        ttk.Label(system, text="System", style="CardHeading.TLabel").pack(anchor="w")
        self._sys_lines = {}
        for key, label in (("ram", "RAM"), ("procs", "Browser processes"),
                           ("sessions", "Active sessions"), ("sync", "Sheet sync")):
            line = ttk.Frame(system, style="Card.TFrame")
            line.pack(fill="x", pady=(S["sm"], 0))
            ttk.Label(line, text=label, style="CardMuted.TLabel").pack(side="left")
            v = ttk.Label(line, text="\u2014", style="CardText.TLabel")
            v.pack(side="right")
            self._sys_lines[key] = v

        alerts = ttk.Frame(row2, style="Card.TFrame", padding=S["lg"])
        alerts.grid(row=0, column=2, sticky="nsew")
        head = ttk.Frame(alerts, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Recent alerts", style="CardHeading.TLabel").pack(side="left")
        ttk.Button(head, text="Open log", command=self._open_log).pack(side="right")
        self._alerts = tk.Text(alerts, height=8, wrap="word", borderwidth=0,
                               highlightthickness=0, font=theme.mono("small"),
                               state="disabled", cursor="arrow")
        self._alerts.pack(fill="both", expand=True, pady=(S["sm"], 0))
        self._alerts.bind("<Button-1>", lambda e: self._open_log())

    # ── Hooks ─────────────────────────────────────────────────

    def set_on_login_pending(self, callback):
        self._on_login_pending = callback

    def set_on_open_log(self, callback):
        self._on_open_log = callback

    def _open_log(self):
        if self._on_open_log:
            self._on_open_log()

    def _on_login_click(self):
        if self._on_login_pending and self._pending_usernames:
            self.set_login_running(True)
            self._on_login_pending(list(self._pending_usernames))

    # ── Data ──────────────────────────────────────────────────

    def refresh(self):
        try:
            total, _linked = db.count_accounts()
            logged_in = len(db.logged_in_profiles())
            pending, unlinked = db.count_pending()
            disabled = db.count_disabled()
            self._pending_usernames = [a["username"] for a in db.pending_accounts()
                                       if a.get("linked_profile")]
        except Exception as e:
            self._login_hint.configure(text=f"Database unavailable: {e}")
            return
        new = {"total": total, "logged_in": logged_in,
               "pending": pending, "disabled": disabled}
        for key, value in new.items():
            effects.count_up(self._stat_labels[key], self._values[key], value,
                             theme.MOTION["count"])
        self._values = new
        n = len(self._pending_usernames)
        self._login_btn.configure(
            text=f"Log in {n} pending account{'s' if n != 1 else ''}",
            state="normal" if n and not self._login_running else "disabled")
        self._login_hint.configure(
            text=(f"{unlinked} pending row{'s' if unlinked != 1 else ''} have no "
                  "Brave profile \u2014 run scripts/provision_profiles.py")
            if unlinked else "")

    def _tick(self):
        try:
            if self.winfo_ismapped():
                self.refresh()
        finally:
            self.after(REFRESH_MS, self._tick)

    def set_login_running(self, running: bool):
        self._login_running = running
        self._login_btn.configure(
            state="disabled" if running or not self._pending_usernames else "normal")
        if running:
            self._login_btn.configure(text="Logging in\u2026")
        else:
            self.refresh()

    def set_run_progress(self, done: int, total: int, text: str):
        if total <= 0:
            self._run_text.configure(text="Idle")
            self._run_count.configure(text="")
            self._run_bar.configure(value=0, maximum=1)
            return
        self._run_text.configure(text=text or "Running")
        self._run_count.configure(text=f"{done}/{total}")
        start = float(self._run_bar.cget("value"))
        self._run_bar.configure(maximum=total)
        effects.tween(self._run_bar, theme.MOTION["progress"],
                      lambda t: self._run_bar.configure(value=start + (done - start) * t),
                      key="bar")

    def set_run_summary(self, text: str):
        self._run_summary.configure(text=text or "No run yet")

    def set_system(self, ram: str, procs: int, sessions: int, sync_age):
        self._sys_lines["ram"].configure(text=ram or "\u2014")
        self._sys_lines["procs"].configure(text=str(procs))
        self._sys_lines["sessions"].configure(text=str(sessions))
        if sync_age is None:
            self._sys_lines["sync"].configure(text="not started")
        else:
            self._sys_lines["sync"].configure(text=f"{int(sync_age)} s ago")

    def add_alert(self, stamp: str, text: str):
        def apply():
            self._alert_lines.insert(0, f"{stamp}  {text}")
            del self._alert_lines[MAX_ALERTS:]
            self._alerts.configure(state="normal")
            self._alerts.delete("1.0", "end")
            self._alerts.insert("end", "\n".join(self._alert_lines))
            self._alerts.configure(state="disabled")
        try:
            self.after(0, apply)
        except tk.TclError:
            pass

    def apply_theme(self, colors: dict):
        self._alerts.configure(bg=colors["card"], fg=colors["error"],
                               insertbackground=colors["fg"])
```

- [ ] **Step 5: Styles and wiring in `main_window.py`**

In `_apply_theme` add:

```python
        style.configure("CardHeading.TLabel", background=c["card"],
                        foreground=c["heading"], font=theme.font("body", "bold"))
        style.configure("CardText.TLabel", background=c["card"],
                        foreground=c["fg"], font=theme.font("body"))
```

In `_build_ui` replace the placeholder dashboard with `self.dashboard_page = DashboardPage(content)` (import at top). In `_connect_callbacks` add:

```python
        self.dashboard_page.set_on_login_pending(self.manager.login_accounts)
        self.dashboard_page.set_on_open_log(lambda: self._show_page("log"))
        self.log_tab.set_on_alert(self.dashboard_page.add_alert)
        from src.storage import config_manager as cfg
        self.dashboard_page.set_run_summary(cfg.get_setting("last_run_summary", ""))
```

(`set_on_login_pending` / `set_on_open_log` wiring goes above the `if not self.manager: return` guard only for the log/summary lines; the manager line stays below it.)

In `_handle_result`: in the `batch_progress` branch add `self.dashboard_page.set_run_progress(result["current"], result["total"], f"{result.get('profile_name', '')}: {result.get('message', '')}".strip(": "))`; in the `batch_result` branch compute `summary = f"{ok} ok \u00b7 {failed} failed \u00b7 {datetime.now():%H:%M}"` from the fields that branch already reads (look at how it logs the totals), then `cfg.save_setting("last_run_summary", summary)`, `self.dashboard_page.set_run_summary(summary)`, `self.dashboard_page.set_run_progress(0, 0, "")`.

In `_update_status_counts`, after computing the RAM segment, push system figures:

```python
        try:
            watcher = getattr(self, "_sheet_watcher", None)
            age = (time.time() - watcher.last_ok) if watcher and watcher.last_ok else None
            self.dashboard_page.set_system(
                self._ram_text.replace("RAM ", "").split("   ")[0] if self._ram_text else "",
                self._ram_procs, self.queue_tab.logged_in_count()[0], age)
        except Exception:
            pass
```

and in `_on_memory_stats` store `self._ram_procs = int(stats.get("browser_processes", stats.get("procs", 0)) or 0)` (check the stats dict keys in `memory_monitor.py:168-200` and use the one that holds the process count). Add `import time` at the top if missing.

- [ ] **Step 6: Run `python verify.py`** — `ALL PROOFS PASS`. Run `python scripts/screenshot_ui.py` and check `hd_light_e_dashboard.png` and `min_dark_c_dashboard.png`: four cards in one row, button under them, three cards below, nothing clipped at 1100×700.

- [ ] **Step 7: Commit**

```bash
git add src/ui/dashboard_page.py src/ui/log_tab.py src/ui/main_window.py verify.py
git commit -m "feat: dashboard with account health, pending-login button, run and system cards"
```

---

## Task 9: `profile_names` on the bulk commands

**Files:**
- Modify: `src/core/driver_manager.py` — `share_to_groups_bulk` (154), `join_group` (167), `fetch_my_groups_bulk` (182), `auto_setup_all_profiles` (205), `accept_all_pending_requests` (219), `watch_url` (251); handlers `_do_fetch_my_groups_bulk` (931), `_do_join_group_bulk` (1141), `_do_accept_all_pending` (1676), `_do_auto_setup_all` (1919), `_do_watch` (3933), `_do_share_to_groups_bulk` (where it derives the profile set from `groups[*]["profiles"]`)
- Modify: `verify.py`

**Interfaces:**
- Produces: every listed helper accepts a trailing keyword `profile_names: list[str] | None = None` and puts it in the command dict; every listed handler uses `profiles = cmd.get("profile_names") or cfg.list_profiles()` (for `_do_share_to_groups_bulk`: when `profile_names` is set, each group's `profiles` list is intersected with it; for `_do_watch`, the `ok` filter still applies on top). `watch_url(url, minutes=None, profile_names=None)` passes it as `cmd["profile_names"]` and `_do_watch(url, minutes, profile_names)` receives it.

- [ ] **Step 1: Proof**

```python
step("profile_names on bulk commands")
_m = _DM()
_m.share_to_groups_bulk("u", [], profile_names=["P1"])
_m.join_group(["g"], profile_names=["P1"])
_m.fetch_my_groups_bulk(profile_names=["P1"])
_m.auto_setup_all_profiles(profile_names=["P1"])
_m.accept_all_pending_requests(profile_names=["P1"])
_m.watch_url("u", None, profile_names=["P1"])
while True:
    try: _c = _m.cmd_queue.get_nowait()
    except _q.Empty: break
    if _c.get("profile_names") != ["P1"]:
        failures.append(f"{_c['type']} dropped profile_names")
print("ok" if not [f for f in failures if "profile_names" in f] else "FAILED")
```

- [ ] **Step 2: Run** — expect `TypeError: ... unexpected keyword argument 'profile_names'`.

- [ ] **Step 3: Implement** — add the keyword to each helper and `"profile_names": profile_names` to its dict. In each handler replace the `cfg.list_profiles()` read with `cmd.get("profile_names") or cfg.list_profiles()`. For `_do_watch`, find the `watch_url` dispatcher branch, pass `cmd.get("profile_names")` as a third argument, and change line 3933 to `profiles = [p for p in (profile_names or cfg.list_profiles()) if p in ok]`. For `_do_share_to_groups_bulk`, after `groups = cmd["groups"]`, add:

```python
        wanted = cmd.get("profile_names")
        if wanted:
            keep = set(wanted)
            groups = [dict(g, profiles=[p for p in g.get("profiles", []) if p in keep])
                      for g in groups]
            groups = [g for g in groups if g["profiles"]]
```

- [ ] **Step 4: Run `python verify.py`** — `ALL PROOFS PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/core/driver_manager.py verify.py
git commit -m "feat: bulk commands accept an explicit profile list"
```

---

## Task 10: Extract the profile dialogs, then build `AccountsPage`

**Files:**
- Create: `src/ui/profile_dialogs.py` — moved verbatim from `profiles_tab.py`: `_show_brave_picker` (807-864) → `pick_brave_profile(parent, brave_profiles) -> dict | None`; `_pick_saved_profile` (362-424) → `pick_saved_profile(parent, account_label) -> str | None`; the modal + thread part of `_on_add` (735-805) and `_on_fetch_fb_name` (920-1016) → `fetch_fb_name_modal(parent, profile_path) -> str | None`; `_on_bulk_fetch_fb_names` (1018-1269) → `bulk_fetch_fb_names(parent, on_complete)`
- Create: `src/ui/accounts_page.py`
- Modify: `src/ui/main_window.py` — `accounts` page becomes `AccountsPage`; `profiles_tab` alias; wiring of `set_on_login_selected`; selection chip
- Modify: `verify.py`

**Interfaces:**
- Consumes: `db.list_accounts` (with `sheet_status`), `db.link_account`, `db.logged_in_profiles`, `cfg.list_profiles / get_profile_path / save_profile / delete_profile / auto_sync_brave_profiles / list_brave_profiles`, `effects.animate_press`, `DriverManager` helpers with `profile_names` (Task 9), `login_accounts` (Task 7)
- Produces `class AccountsPage(ttk.Frame)` with the full `ProfilesTab` surface used by `MainWindow`: `set_on_launch_profile`, `set_on_auto_setup`, `set_on_auto_setup_all`, `set_on_accept_all_pending`, `set_on_check_login_status`, **new** `set_on_login_selected` (`cb(usernames)`), `set_on_selection_change` (`cb(profiles: list[str])`), `_log_callback`, `selected_profile` property, `selected_accounts() -> list[dict]`, `selected_profiles() -> list[str]`, `set_status(text, logged_in=False)`, `set_launch_enabled`, `set_check_login_enabled`, `set_login_enabled`, `mark_login_status`, `mark_rate_limited`, `set_auto_setup_status`, `set_auto_setup_enabled`, `refresh_accounts()`, `refresh_profiles()`, `apply_theme(colors)`
- Callback signatures the page calls: `_on_auto_setup_all_cb(target_friends=0, pinterest_query=None, bio=None, connect_friends=True, profile_names=[...])`, `_on_accept_all_pending_cb(profile_names=[...])`, `_on_check_login_status_cb(profile_names=[...] or None)`, `_on_login_selected_cb(usernames)`, `_on_auto_setup_cb(profile_name, target_friends=0, pinterest_query=None, bio=None)`, `_on_launch_profile_cb(profile_name)`

- [ ] **Step 1: Proof** — in `verify.py` change the smoke test's tab tuple to include `"profiles_tab"` (already) and add after the page loop:

```python
    from src.ui.accounts_page import AccountsPage as _AP
    if not isinstance(app.profiles_tab, _AP):
        failures.append("accounts page is not AccountsPage")
    app.profiles_tab.refresh_accounts(); app.update_idletasks()
    _tree = app.profiles_tab._tree
    _rows = _tree.get_children()
    if _rows:
        app.profiles_tab._toggle_row(_rows[0])
        if len(app.profiles_tab.selected_accounts()) + len(app.profiles_tab.selected_profiles()) == 0:
            failures.append("toggling a row selected nothing")
        app.profiles_tab._toggle_row(_rows[0])
    if not callable(getattr(app.profiles_tab, "set_on_login_selected", None)):
        failures.append("AccountsPage.set_on_login_selected missing")
```

- [ ] **Step 2: Run** — expect `ModuleNotFoundError: src.ui.accounts_page`.

- [ ] **Step 3: Create `src/ui/profile_dialogs.py`** by moving the four routines out of `profiles_tab.py`. Each becomes a module-level function taking `parent` where the method used `self`; every `self._log_callback(...)` becomes a `log` parameter defaulting to `print`; `messagebox` calls keep `parent=parent`. The bulk fetch's `_on_complete` closure calls the passed `on_complete()` instead of `self.refresh_profiles()`. Keep every comment. Make `ProfilesTab` call the new functions (so the old tab keeps working until it is deleted in Task 12) and run `python verify.py` — `ALL PROOFS PASS` — before writing the page.

- [ ] **Step 4: Create `src/ui/accounts_page.py`**

```python
"""Accounts page: one table of every roster row and every saved Brave
profile, a checkbox column that is the selection every bulk action reads,
and the action bar that replaces the old profile rail.

The old tab kept two lists (Brave profiles, roster) and two ideas of scope
- a "Logged in only" filter over one list and buttons that enumerated the
other. Here there is one list and one scope: the checked rows.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from src.storage import config_manager as cfg
from src.storage import database as db
from src.ui import effects, theme
from src.ui.profile_dialogs import (bulk_fetch_fb_names, fetch_fb_name_modal,
                                    pick_brave_profile, pick_saved_profile)

FILTERS = ("All", "Logged in", "Needs login", "Pending", "Disabled")
CHECKED, UNCHECKED = "\u2611", "\u2610"


class AccountsPage(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._log_callback = print
        self._on_launch_profile_cb = None
        self._on_auto_setup_cb = None
        self._on_auto_setup_all_cb = None
        self._on_accept_all_pending_cb = None
        self._on_check_login_status_cb = None
        self._on_login_selected_cb = None
        self._on_selection_change_cb = None
        self._rows: dict[str, dict] = {}       # iid -> row dict
        self._checked: set[str] = set()         # iids
        self._live: dict[str, bool] = {}        # profile -> last live verdict
        self._rate_limited: set[str] = set()
        self._login_running = False
        self._scan_running = False
        self._setup_running = False
        self._search_var = tk.StringVar(value=cfg.get_setting("accounts_search", ""))
        self._filter_var = tk.StringVar(value=cfg.get_setting("accounts_filter", "All"))
        self._status_var = tk.StringVar(value="")
        self._setup_status_var = tk.StringVar(value="")
        self._build_ui()
        self.refresh_accounts()

    # ── Build ─────────────────────────────────────────────────

    def _build_ui(self):
        S = theme.SPACE
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", padx=S["lg"], pady=(S["lg"], S["sm"]))
        ttk.Label(bar, text="Search").pack(side="left")
        search = ttk.Entry(bar, textvariable=self._search_var, width=28)
        search.pack(side="left", padx=(S["xs"], S["md"]))
        search.bind("<KeyRelease>", lambda e: self._on_filter_change())
        ttk.Label(bar, text="Show").pack(side="left")
        combo = ttk.Combobox(bar, textvariable=self._filter_var, values=FILTERS,
                             state="readonly", width=12)
        combo.pack(side="left", padx=(S["xs"], S["md"]))
        combo.bind("<<ComboboxSelected>>", lambda e: self._on_filter_change())
        ttk.Button(bar, text="Select all", command=self._select_all).pack(side="left")
        ttk.Button(bar, text="Clear", command=self._clear_selection).pack(
            side="left", padx=(S["xs"], 0))
        self._count_lbl = ttk.Label(bar, textvariable=self._status_var, style="Muted.TLabel")
        self._count_lbl.pack(side="right")

        table = ttk.Frame(self)
        table.grid(row=1, column=0, sticky="nsew", padx=S["lg"])
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        cols = ("check", "no", "name", "username", "profile", "status", "reason")
        self._tree = ttk.Treeview(table, columns=cols, show="headings",
                                  selectmode="none")
        heads = {"check": (CHECKED, 36, "center"), "no": ("#", 48, "e"),
                 "name": ("Name", 200, "w"), "username": ("Username", 220, "w"),
                 "profile": ("Brave profile", 200, "w"),
                 "status": ("Status", 130, "w"), "reason": ("Reason", 180, "w")}
        for c in cols:
            text, width, anchor = heads[c]
            self._tree.heading(c, text=text, anchor=anchor,
                               command=lambda c=c: self._on_heading(c))
            self._tree.column(c, width=width, minwidth=36 if c == "check" else 60,
                              anchor=anchor, stretch=c in ("name", "username", "profile"))
        vsb = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<Button-1>", self._on_click)
        self._tree.bind("<space>", lambda e: self._toggle_focused())

        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky="ew", padx=S["lg"], pady=S["md"])
        flow = effects.FlowFrame(actions)
        flow.pack(fill="x")

        def btn(text, cmd, accent=False, state="normal"):
            b = ttk.Button(flow, text=text, command=cmd, state=state,
                           style="Accent.TButton" if accent else "TButton")
            if accent:
                effects.animate_press(b)
            return flow.add(b)

        self.login_btn = btn("Log in selected", self._on_login_selected, accent=True,
                             state="disabled")
        self.check_login_btn = btn("Check login status", self._on_check_login_status)
        self.setup_all_btn = btn("Auto setup", self._on_auto_setup_all, state="disabled")
        self.accept_btn = btn("Accept friend requests", self._on_accept_all_pending,
                              state="disabled")
        self.bulk_fetch_btn = btn("Update FB names", self._on_bulk_fetch_fb_names)
        self.add_btn = btn("+ Add Brave profile", self._on_add)
        self.scan_btn = btn("Scan for new profiles", self._on_scan)
        self.launch_btn = btn("Launch", self._on_launch, state="disabled")
        self.fetch_btn = btn("Update FB name", self._on_fetch_fb_name, state="disabled")
        self.setup_btn = btn("Auto setup (one)", self._on_auto_setup, state="disabled")
        self.delete_btn = btn("Remove", self._on_delete, state="disabled")
        self.link_btn = btn("Link to Brave profile\u2026", self._on_link_account,
                            state="disabled")
        self.unlink_btn = btn("Unlink", self._on_unlink_account, state="disabled")

        foot = ttk.Frame(self)
        foot.grid(row=3, column=0, sticky="ew", padx=S["lg"], pady=(0, S["md"]))
        self.status_dot = ttk.Label(foot, text="\u25cf", style="StatusDot.TLabel")
        self.status_dot.pack(side="left")
        self._status_text = ttk.Label(foot, text="", style="Status.TLabel")
        self._status_text.pack(side="left", padx=(S["xs"], S["lg"]))
        ttk.Label(foot, textvariable=self._setup_status_var,
                  style="Muted.TLabel").pack(side="left")
        self.set_status("No profile loaded")

    # ── Hooks (names asserted by verify.py) ───────────────────

    def set_on_launch_profile(self, callback): self._on_launch_profile_cb = callback
    def set_on_auto_setup(self, callback): self._on_auto_setup_cb = callback
    def set_on_auto_setup_all(self, callback): self._on_auto_setup_all_cb = callback
    def set_on_accept_all_pending(self, callback): self._on_accept_all_pending_cb = callback
    def set_on_check_login_status(self, callback): self._on_check_login_status_cb = callback
    def set_on_login_selected(self, callback): self._on_login_selected_cb = callback
    def set_on_selection_change(self, callback): self._on_selection_change_cb = callback

    # ── Selection model ───────────────────────────────────────

    def selected_accounts(self) -> list[dict]:
        return [self._rows[i]["account"] for i in self._tree.get_children()
                if i in self._checked and self._rows[i]["account"]]

    def selected_profiles(self) -> list[str]:
        return [self._rows[i]["profile"] for i in self._tree.get_children()
                if i in self._checked and self._rows[i]["profile"]]

    @property
    def selected_profile(self) -> str | None:
        profiles = self.selected_profiles()
        return profiles[0] if len(profiles) == 1 else None

    @property
    def selected_account(self) -> dict | None:
        accounts = self.selected_accounts()
        return accounts[0] if len(accounts) == 1 else None

    def _toggle_row(self, iid: str):
        if iid in self._checked:
            self._checked.discard(iid)
        else:
            self._checked.add(iid)
        self._tree.set(iid, "check", CHECKED if iid in self._checked else UNCHECKED)
        self._selection_changed()

    def _toggle_focused(self):
        iid = self._tree.focus()
        if iid:
            self._toggle_row(iid)

    def _select_all(self):
        for iid in self._tree.get_children():
            self._checked.add(iid)
            self._tree.set(iid, "check", CHECKED)
        self._selection_changed()

    def _clear_selection(self):
        for iid in self._tree.get_children():
            self._tree.set(iid, "check", UNCHECKED)
        self._checked.clear()
        self._selection_changed()

    def _selection_changed(self):
        self._update_buttons()
        if self._on_selection_change_cb:
            self._on_selection_change_cb(self.selected_profiles())

    def _on_click(self, event):
        region = self._tree.identify_region(event.x, event.y)
        if region == "heading":
            return
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        col = self._tree.identify_column(event.x)
        if col == "#1":
            self._toggle_row(iid)
        else:
            self._tree.focus(iid)

    def _on_heading(self, col):
        if col == "check":
            visible = self._tree.get_children()
            if all(i in self._checked for i in visible):
                self._clear_selection()
            else:
                self._select_all()

    # ── Data ──────────────────────────────────────────────────

    def refresh_accounts(self):
        """Rebuild the table from the database plus unlinked Brave profiles."""
        keep = {self._rows[i]["key"] for i in self._checked if i in self._rows}
        self._rows.clear()
        self._checked.clear()
        self._tree.delete(*self._tree.get_children())
        try:
            accounts = db.list_accounts()
        except Exception as e:
            accounts = []
            self._status_var.set(f"Database error: {e}")
        linked = {a["linked_profile"] for a in accounts if a.get("linked_profile")}
        rows = [self._row_for(a, a.get("linked_profile") or "") for a in accounts]
        for p in cfg.list_profiles():
            if p not in linked:
                rows.append(self._row_for(None, p))
        needle = self._search_var.get().strip().lower()
        mode = self._filter_var.get()
        shown = 0
        for r in rows:
            if needle and needle not in r["haystack"]:
                continue
            if not self._passes(r, mode):
                continue
            iid = self._tree.insert("", "end", values=(
                UNCHECKED, r["no"], r["name"], r["username"], r["profile"] or "\u2014",
                r["status_text"], r["reason"]), tags=(r["tag"],))
            self._rows[iid] = r
            shown += 1
            if r["key"] in keep:
                self._checked.add(iid)
                self._tree.set(iid, "check", CHECKED)
        total = len(rows)
        self._status_var.set(f"{shown} of {total} row{'s' if total != 1 else ''}")
        self._selection_changed()

    def refresh_profiles(self):
        self.refresh_accounts()

    def _row_for(self, account: dict | None, profile: str) -> dict:
        a = account or {}
        status = a.get("status") or ""
        sheet = a.get("sheet_status") or ""
        live = self._live.get(profile)
        if status == "disabled":
            kind, text = "disabled", "\u2715 Disabled"
        elif profile in self._rate_limited:
            kind, text = "warn", "\u26a0 Rate limited"
        elif live is False:
            kind, text = "off", "\u25cb Not logged in"
        elif live is True or status == "ok":
            kind, text = "ok", "\u25cf Logged in"
        elif account is not None and sheet == "":
            kind, text = "pending", "\u25cb Pending"
        elif account is None:
            kind, text = "off", "\u25cb Unlinked profile"
        else:
            kind, text = "off", "\u25cb Not logged in"
        username = a.get("username", "")
        return {
            "key": username or f"profile:{profile}",
            "account": account, "profile": profile,
            "no": a.get("sheet_no") if a.get("sheet_no") is not None else "",
            "name": a.get("facebook_name") or (profile if account is None else ""),
            "username": username or "\u2014",
            "status": status, "sheet_status": sheet, "kind": kind,
            "status_text": text, "reason": a.get("status_reason") or "",
            "tag": kind,
            "haystack": " ".join((a.get("facebook_name", ""), username,
                                  a.get("gmail", ""), profile)).lower(),
        }

    @staticmethod
    def _passes(row: dict, mode: str) -> bool:
        k = row["kind"]
        return (mode == "All" or
                (mode == "Logged in" and k == "ok") or
                (mode == "Needs login" and k in ("off", "pending", "warn")) or
                (mode == "Pending" and k == "pending") or
                (mode == "Disabled" and k == "disabled"))

    def _on_filter_change(self):
        cfg.save_setting("accounts_search", self._search_var.get())
        cfg.save_setting("accounts_filter", self._filter_var.get())
        self.refresh_accounts()

    # ── State pushed in by MainWindow ─────────────────────────

    def set_status(self, text: str, logged_in: bool = False):
        c = theme.get()
        self._status_text.configure(text=text)
        self.status_dot.configure(foreground=c["success"] if logged_in else c["muted"])

    def set_launch_enabled(self, enabled: bool):
        self.launch_btn.configure(state="normal" if enabled and self.selected_profile else "disabled")

    def set_check_login_enabled(self, enabled: bool):
        self._scan_running = not enabled
        self._update_buttons()

    def set_login_enabled(self, enabled: bool):
        self._login_running = not enabled
        self._update_buttons()

    def mark_login_status(self, profile_name: str, logged_in: bool):
        self._live[profile_name] = logged_in
        self.refresh_accounts()

    def mark_rate_limited(self, profile_name: str):
        self._rate_limited.add(profile_name)
        self.refresh_accounts()

    def set_auto_setup_status(self, text: str):
        self._setup_status_var.set(text)

    def set_auto_setup_enabled(self, enabled: bool):
        self._setup_running = not enabled
        self._update_buttons()

    def apply_theme(self, colors: dict):
        c = colors
        self._tree.tag_configure("ok", foreground=c["success"])
        self._tree.tag_configure("pending", foreground=c["warning"])
        self._tree.tag_configure("off", foreground=c["muted"])
        self._tree.tag_configure("disabled", foreground=c["error"])
        self._tree.tag_configure("warn", foreground=c["warning"])
        self.set_status(self._status_text.cget("text"),
                        str(self.status_dot.cget("foreground")) == c["success"])

    def _update_buttons(self):
        profiles = self.selected_profiles()
        accounts = self.selected_accounts()
        one = len(profiles) == 1
        busy = self._login_running or self._scan_running or self._setup_running
        def st(cond): return "normal" if cond and not busy else "disabled"
        self.login_btn.configure(state=st(bool(accounts)))
        self.check_login_btn.configure(state=st(True))
        self.setup_all_btn.configure(state=st(bool(profiles)))
        self.accept_btn.configure(state=st(bool(profiles)))
        self.bulk_fetch_btn.configure(state=st(True))
        self.add_btn.configure(state=st(True))
        self.scan_btn.configure(state=st(True))
        self.launch_btn.configure(state=st(one))
        self.fetch_btn.configure(state=st(one))
        self.setup_btn.configure(state=st(one))
        self.delete_btn.configure(state=st(one))
        acct = self.selected_account
        self.link_btn.configure(state=st(acct is not None and not acct.get("linked_profile")))
        self.unlink_btn.configure(state=st(acct is not None and bool(acct.get("linked_profile"))))

    # ── Actions ───────────────────────────────────────────────

    def _on_login_selected(self):
        usernames = [a["username"] for a in self.selected_accounts()
                     if a.get("linked_profile") and a.get("status") != "disabled"]
        skipped = len(self.selected_accounts()) - len(usernames)
        if not usernames:
            messagebox.showinfo("Log in selected",
                                "None of the checked rows has a Brave profile.",
                                parent=self)
            return
        if not messagebox.askyesno(
                "Log in selected",
                f"Log in {len(usernames)} account(s) now?"
                + (f"\n{skipped} checked row(s) have no Brave profile and are skipped." if skipped else "")
                + "\n\nBrave must be closed. One account at a time, headless.",
                parent=self):
            return
        self.set_login_enabled(False)
        self.set_status(f"Logging in {len(usernames)} account(s)...")
        if self._on_login_selected_cb:
            self._on_login_selected_cb(usernames)

    def _on_check_login_status(self):
        if not self._on_check_login_status_cb:
            return
        profiles = self.selected_profiles() or None
        if profiles is None and not cfg.list_profiles():
            self.set_status("No profiles to check")
            return
        self.set_status("Checking login status...")
        self.set_check_login_enabled(False)
        self._on_check_login_status_cb(profile_names=profiles)

    def _on_auto_setup_all(self):
        profiles = self.selected_profiles()
        if not profiles or not self._on_auto_setup_all_cb:
            return
        if not messagebox.askyesno("Auto setup",
                                   f"Run auto setup (auto-connect friends) on "
                                   f"{len(profiles)} profile(s)?", parent=self):
            return
        self.set_auto_setup_enabled(False)
        self.set_auto_setup_status(f"Running on {len(profiles)} profile(s)...")
        self._on_auto_setup_all_cb(target_friends=0, pinterest_query=None, bio=None,
                                   connect_friends=True, profile_names=profiles)

    def _on_accept_all_pending(self):
        profiles = self.selected_profiles()
        if not profiles or not self._on_accept_all_pending_cb:
            return
        self.set_auto_setup_enabled(False)
        self.set_auto_setup_status(f"Accepting requests on {len(profiles)} profile(s)...")
        self._on_accept_all_pending_cb(profile_names=profiles)

    def _on_auto_setup(self):
        name = self.selected_profile
        if not name or not self._on_auto_setup_cb:
            return
        self.set_auto_setup_enabled(False)
        self.set_auto_setup_status(f"Running auto setup on '{name}'...")
        self._on_auto_setup_cb(name, target_friends=0, pinterest_query=None, bio=None)

    def _on_launch(self):
        name = self.selected_profile
        if name and self._on_launch_profile_cb:
            self.set_launch_enabled(False)
            self.set_status(f"Launching '{name}'...")
            self._on_launch_profile_cb(name)

    def _on_scan(self):
        new = cfg.auto_sync_brave_profiles()
        self.refresh_accounts()
        self.set_status(f"Scan done: {len(new)} new profile(s)" if new else "Scan done: nothing new")
        if new:
            messagebox.showinfo("Scan for new profiles",
                                "Added:\n" + "\n".join(new), parent=self)

    def _on_add(self):
        profiles = cfg.list_brave_profiles()
        picked = pick_brave_profile(self, profiles)
        if not picked:
            return
        fb_name = fetch_fb_name_modal(self, picked["path"], log=self._log_callback)
        base = f"{picked['name']} - {fb_name}" if fb_name else picked["name"]
        name, n = base, 2
        while name in cfg.list_profiles():
            name, n = f"{base} ({n})", n + 1
        cfg.save_profile(name, picked["path"])
        self.refresh_accounts()
        messagebox.showinfo("Profile added", f"Saved '{name}'.", parent=self)

    def _on_fetch_fb_name(self):
        name = self.selected_profile
        if not name:
            return
        path = cfg.get_profile_path(name)
        fb_name = fetch_fb_name_modal(self, path, log=self._log_callback)
        if not fb_name:
            messagebox.showwarning("Update FB name",
                                   "Could not read the Facebook name (not logged in?).",
                                   parent=self)
            return
        new = f"{name.split(' - ')[0]} - {fb_name}"
        if new != name:
            cfg.save_profile(new, path)
            cfg.delete_profile(name)
            config = cfg._load_config()
            urls = config.get("facebook_urls", {})
            if name in urls:
                urls[new] = urls.pop(name)
                cfg._save_config(config)
        self.refresh_accounts()

    def _on_bulk_fetch_fb_names(self):
        bulk_fetch_fb_names(self, on_complete=self.refresh_accounts,
                            log=self._log_callback)

    def _on_delete(self):
        name = self.selected_profile
        if not name:
            return
        if messagebox.askyesno("Remove profile",
                               f"Remove '{name}' from the app? The Brave profile on "
                               f"disk is not touched.", parent=self):
            cfg.delete_profile(name)
            self.refresh_accounts()

    def _on_link_account(self):
        acct = self.selected_account
        if not acct:
            return
        label = acct.get("facebook_name") or acct["username"]
        profile = pick_saved_profile(self, label)
        if profile:
            db.link_account(acct["username"], profile)
            self.refresh_accounts()

    def _on_unlink_account(self):
        acct = self.selected_account
        if acct and acct.get("linked_profile"):
            db.link_account(acct["username"], "")
            self.refresh_accounts()
```

Check `cfg.list_brave_profiles()` / `auto_sync_brave_profiles()` return shapes in `src/storage/config_manager.py` and match the dict keys (`name`, `path`) and the list-of-names the old tab used (`profiles_tab.py:717-805, 873-886`).

- [ ] **Step 5: Host it in `main_window.py`**

Replace the `accounts_host`/`ProfilesTab` lines with:

```python
        self.accounts_page = AccountsPage(content)
        self.profiles_tab = self.accounts_page        # name kept for verify.py
```

and `"accounts": self.accounts_page` in `_pages`. Remove the `ProfilesTab` and `ScrollFrame` imports if now unused. In `_connect_callbacks` add `self.profiles_tab.set_on_login_selected(self.manager.login_accounts)` (below the manager guard) and, above it, `self.profiles_tab.set_on_selection_change(self._on_selection_change)` with:

```python
    def _on_selection_change(self, profiles: list[str]):
        n = len(profiles)
        if n:
            self.set_selection_chip(f"{n} selected")
        else:
            active = len(self.queue_tab.logged_in_count() and
                         __import__("src.storage.database", fromlist=["x"]).logged_in_profiles())
            self.set_selection_chip(f"all logged in ({active})")
```

(Write the `active` line as `from src.storage import database as db` at the top of the file and `active = len(db.logged_in_profiles())` — no `__import__`.)

In `_apply_theme` add Treeview styles:

```python
        style.configure("Treeview", background=c["list_bg"], fieldbackground=c["list_bg"],
                        foreground=c["list_fg"], borderwidth=0,
                        rowheight=self.px(26), font=theme.font("body"))
        style.map("Treeview", background=[("selected", c["list_select_bg"])],
                  foreground=[("selected", c["list_select_fg"])])
        style.configure("Treeview.Heading", background=c["surface"],
                        foreground=c["muted"], relief="flat",
                        font=theme.font("small", "bold"), padding=(6, 4))
        style.map("Treeview.Heading", background=[("active", c["surface"])])
```

- [ ] **Step 6: Run `python verify.py`** — `ALL PROOFS PASS`. `python scripts/screenshot_ui.py`; check `hd_light_e_accounts.png` and `min_dark_c_accounts.png`: table fills the height, action bar wraps at 1100 px, no clipping.

- [ ] **Step 7: Commit**

```bash
git add src/ui/profile_dialogs.py src/ui/accounts_page.py src/ui/profiles_tab.py src/ui/main_window.py verify.py
git commit -m "feat: accounts page with a checkbox table as the selection model"
```

---

## Task 11: Queue and Compose act on the selection

**Files:**
- Modify: `src/ui/queue_tab.py` — `__init__` (add `self._selection = None`), `set_selection_source`, `_displayed_profiles` (582-593), `_on_watch` (505-527), button labels at 135-138, 175-178, 301-306, 374-378
- Modify: `src/ui/share_tab.py` — `__init__`, `set_selection_source`, `_on_bulk_share_to_groups` (714-728), `_on_join` (730-745), `_on_fetch_groups` (499-504), labels at 136-140, 267-271, 277-280
- Modify: `src/ui/main_window.py` — `_connect_callbacks`
- Modify: `verify.py`

**Interfaces:**
- Produces: `QueueTab.set_selection_source(fn)` and `ShareTab.set_selection_source(fn)` where `fn() -> list[str]`; when it returns a non-empty list, that list is the target set; otherwise the current behaviour (all logged-in / all profiles). Callback calls gain `profile_names=`: `_on_watch_url_cb(url, minutes, profile_names=...)`, `_on_bulk_share_cb(post_url, groups, comment, reaction, profile_names=...)`, `_on_join_group_cb(urls, profile_names=...)`, `_on_fetch_groups_cb(profile_names=...)`.

- [ ] **Step 1: Proof** — in the smoke test after the AccountsPage checks:

```python
    if app.queue_tab._selection is None or app.share_tab._selection is None:
        failures.append("selection source not wired into queue/share tabs")
    for w in _walk(app):
        if isinstance(w, _ttk.Button) and "(All Profiles)" in str(w.cget("text")):
            failures.append(f"button still scoped by label: {w.cget('text')}")
```

- [ ] **Step 2: Run** — expect `selection source not wired` and label failures.

- [ ] **Step 3: Implement**

`queue_tab.py`:

```python
    def set_selection_source(self, fn):
        """fn() -> checked Brave profiles on the Accounts page; [] = default scope."""
        self._selection = fn

    def _targets(self) -> list[str]:
        sel = self._selection() if self._selection else []
        return list(sel) if sel else []
```

`_displayed_profiles`: first line becomes `profiles = self._targets() or cfg.list_profiles()`; keep the logged-in filter only when `not self._targets()`. `_on_watch`: `self._on_watch_url_cb(url, minutes, profile_names=self._targets() or None)`. Labels: `"Add to Queue (All Profiles)"` → `"Add to Queue"` (both), `"Add to Queue (All URLs x All Accounts)"` → `"Add to Queue (all URLs)"`, `"Post to All Profiles"` → `"Add text post"`. The heading `"Quick Add — All Profiles"` → `"Quick Add"`.

`share_tab.py`: same `set_selection_source` / `_targets`; `_on_bulk_share_to_groups` passes `profile_names=self._targets() or None`; `_on_join` passes `profile_names=self._targets() or None`; `_on_fetch_groups` passes `profile_names=self._targets() or None`. Labels: `"Share Selected Groups (All Profiles)"` → `"Share to selected groups"`, `"Share Selected Groups (This Profile)"` → `"Share to selected groups (one profile)"`, `"Fetch My Groups (All Profiles)"` → `"Fetch my groups"`. Status strings `"across all profiles"` → `"across the selected profiles"`.

`main_window.py` `_connect_callbacks`: `self.queue_tab.set_selection_source(self.profiles_tab.selected_profiles)` and the same for `share_tab`, above the manager guard.

- [ ] **Step 4: Run `python verify.py`** — `ALL PROOFS PASS`.

- [ ] **Step 5: Commit**

```bash
git add src/ui/queue_tab.py src/ui/share_tab.py src/ui/main_window.py verify.py
git commit -m "feat: queue and compose act on the accounts selection"
```

---

## Task 12: Remove `profiles_tab.py`, update docs and memory

**Files:**
- Delete: `src/ui/profiles_tab.py`
- Modify: `README.md` (Run section, Utility scripts table, Layout block), `verify.py` (nothing should import profiles_tab)
- Modify: the two memory files that describe the shell (`fb-tool-architecture.md`, `fb-tool-ui-conventions.md`) under `C:\Users\M2CarsPH\.claude\projects\C--Users-M2CarsPH-Desktop-FB-TOOL-AUTOMATION-MAIN\memory\`

- [ ] **Step 1:** `grep -rn "profiles_tab" src scripts verify.py` — the only hits must be the `MainWindow.profiles_tab` alias and `verify.py`'s attribute names. Delete `src/ui/profiles_tab.py` and any import of `ProfilesTab`.

- [ ] **Step 2: Run `python verify.py`** — `ALL PROOFS PASS`; `python scripts/screenshot_ui.py` — 48 files, spot-check four.

- [ ] **Step 3: README** — replace the Run section's tab description with the six pages; add `scripts/screenshot_ui.py` to the Utility scripts table; add `src/ui/sidebar.py`, `dashboard_page.py`, `accounts_page.py`, `profile_dialogs.py`, `assets/` to the Layout block; document the pending-login button and `ui_animations` / `ui_sidebar_collapsed` settings.

- [ ] **Step 4: Memory** — update `fb-tool-architecture.md`'s UI shell paragraph to the new shell (sidebar, pages, no drawer, selection model, `login_accounts` command) and note the spec/plan paths; in `fb-tool-ui-conventions.md` add the motion rule (all animation through `effects.tween`, `theme.MOTION`) and the brand-red rule.

- [ ] **Step 5: Commit**

```bash
git add README.md verify.py
git rm src/ui/profiles_tab.py
git commit -m "refactor: retire profiles_tab now that the accounts page owns its surface"
```

---

## Self-review

**Spec coverage.** Shell/sidebar/logo/header/no drawer → Tasks 3-4. Motion table: page slide, sidebar tween, press pulse, theme dip, count-up, progress tween → Tasks 2, 4, 5, 8. Dashboard cards and button → Task 8. Accounts table, filters, actions, selection model, chip → Tasks 10-11. `sheet_status` mirror, `pending_accounts`, `SheetWriter`, `login_accounts` command, result handling → Tasks 6-7. `profile_names` on bulk commands → Task 9. Removal of `profiles_tab.py`, README → Task 12. Screenshot pass → `scripts/screenshot_ui.py` (Task 4), run at the end of Tasks 4, 8, 10, 12. Auto-collapse below `px(1200)` from the spec is **not** in any task — deferred deliberately: the operator pins the state, and a `<Configure>` auto-toggle fighting a manual toggle is a worse experience than none; noted here so it is a decision, not an omission.

**Placeholder scan.** Task 5 Step 1 has a leftover `_accent = [...]` line — harmless but delete it when writing the proof. Task 10 Step 5's `_on_selection_change` block contains an `__import__` sketch immediately corrected by the note beneath; the executor writes the corrected form.

**Type consistency.** `selected_profiles() -> list[str]` (Task 10) is what `set_selection_source` consumes (Task 11) and what `_on_selection_change(profiles: list[str])` receives. `login_accounts(usernames: list[str])` (Task 7) is what `DashboardPage.set_on_login_pending` and `AccountsPage.set_on_login_selected` call with. `profile_names=` keyword (Task 9) matches every call in Tasks 10-11. `theme.MOTION` keys used: `page`, `sidebar`, `press`, `theme`, `count`, `progress` — all defined in Task 1.
