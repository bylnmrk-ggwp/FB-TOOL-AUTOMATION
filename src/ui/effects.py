"""Reusable micro-interaction helpers for the flat UI.

These helpers add polish to raw-tk widgets (Listbox, tk.Button):

  - attach_listbox_hover(): highlights the row under the cursor without
    disturbing the current selection. Colors are read live from the active
    theme, so a mid-session theme switch re-themes the hover instantly.
  - attach_button_hover(): adds hover feedback to a raw tk.Button (ttk
    buttons already get hover/pressed feedback from their style maps).
  - register_wheel_target() / install_wheel_router(): one app-wide
    MouseWheel binding that routes scrolling to whichever registered
    canvas is under the pointer. Replaces the per-tab bind_all /
    unbind_all pattern, which broke scrolling app-wide whenever one
    widget unbound the shared event.
  - tween() and friends (slide_in, animate_press, count_up, blend): the one
    animation clock every motion in the UI runs on; see the Motion section.

Returns a `clear()` callable for listboxes — call it from apply_theme()
after re-theming, or after repopulating the listbox contents.
"""

import time
import tkinter as tk
from tkinter import ttk

from src.ui import theme

# ── Mousewheel routing ─────────────────────────────────────

# Canvases that want wheel scrolling, in registration order.
_WHEEL_TARGETS: list = []


def wait_for_thread(widget, thread, timeout: float = 60.0,
                    poll_ms: int = 50) -> bool:
    """Wait for a worker thread without freezing Tk.

    thread.join() blocks the event loop, so a modal progress dialog cannot
    repaint and an indeterminate Progressbar never animates while the worker
    runs. This pumps the event loop instead. Only call it while a modal grab
    is held, so the pumped events cannot re-enter unrelated handlers.

    Returns True if the thread finished, False on timeout or if the widget
    was destroyed while waiting.
    """
    deadline = time.monotonic() + timeout
    while thread.is_alive():
        if time.monotonic() >= deadline:
            return False
        try:
            widget.update()
        except tk.TclError:
            return False
        time.sleep(poll_ms / 1000.0)
    return True


def register_wheel_target(canvas):
    """Register a tk.Canvas to receive wheel scrolling when the pointer
    is over it (or over any of its descendants). Auto-unregisters when
    the canvas is destroyed (e.g. transient dialogs)."""
    if canvas not in _WHEEL_TARGETS:
        _WHEEL_TARGETS.append(canvas)
        canvas.bind("<Destroy>",
                    lambda e: unregister_wheel_target(canvas), add="+")


def unregister_wheel_target(canvas):
    """Remove a canvas from the router (call before destroying it)."""
    try:
        _WHEEL_TARGETS.remove(canvas)
    except ValueError:
        pass


def install_wheel_router(root):
    """Install ONE root-level MouseWheel binding that scrolls the
    registered canvas under the pointer. Widgets that scroll natively
    (Listbox, Text) are left alone so they don't double-scroll."""

    def _route(event):
        try:
            under = root.winfo_containing(event.x_root, event.y_root)
            if under is None:
                return
            # Native scrollers (Listbox/Text) handle their own wheel — BUT
            # only defer to them when they actually have content to scroll.
            # A short list that fits its view (yview() == (0.0, 1.0)) must
            # fall through so the enclosing ScrollFrame scrolls instead of
            # becoming a dead zone under the pointer.
            if isinstance(under, (tk.Listbox, tk.Text)):
                try:
                    first, last = under.yview()
                    if not (first <= 0.0 and last >= 1.0):
                        return  # list can scroll — let it
                except Exception:
                    return
            # Walk up the widget tree to the nearest registered canvas.
            w = under
            while w is not None:
                if w in _WHEEL_TARGETS:
                    if w.winfo_exists():
                        w.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return
                w = getattr(w, "master", None)
        except Exception:
            pass

    root.bind_all("<MouseWheel>", _route)


def attach_listbox_hover(listbox, hover_bg=None, hover_fg=None):
    """Highlight the row under the cursor on a tk.Listbox.

    Selected rows keep their selection colors (hover never overrides the
    user's selection). Returns a zero-arg `clear()` callable.
    """
    state = {"index": -1}

    def _restore(idx):
        if idx < 0:
            return
        try:
            colors = theme.get()
            if listbox.select_includes(idx):
                bg = colors["list_select_bg"]
                fg = colors["list_select_fg"]
            else:
                bg = colors["list_bg"]
                fg = colors["list_fg"]
            listbox.itemconfig(idx, bg=bg, fg=fg)
        except (tk.TclError, ValueError):
            pass

    def clear(event=None):
        _restore(state["index"])
        state["index"] = -1

    def _on_motion(event):
        size = listbox.size()
        if size == 0:
            return
        idx = listbox.nearest(event.y)
        if idx < 0 or idx >= size:
            clear()
            return
        if idx == state["index"]:
            return
        clear()
        if listbox.select_includes(idx):
            return  # keep selection colors on selected rows
        try:
            colors = theme.get()
            listbox.itemconfig(
                idx,
                bg=hover_bg or colors["list_hover_bg"],
                fg=hover_fg or colors["list_hover_fg"],
            )
            state["index"] = idx
        except (tk.TclError, ValueError):
            pass

    listbox.bind("<Motion>", _on_motion, add="+")
    listbox.bind("<Leave>", lambda e: clear(), add="+")
    listbox.bind("<<ListboxSelect>>", clear, add="+")
    return clear


def attach_button_hover(button, hover_bg=None, hover_fg=None):
    """Add hover feedback to a raw tk.Button (not ttk).

    The button is themed with the active palette's secondary colors (so
    it fits both light and dark mode) and brightens on hover.
    """
    def _base_colors():
        colors = theme.get()
        return colors["secondary"], colors["secondary_fg"]

    def _apply_base():
        bg, fg = _base_colors()
        button.configure(background=bg, foreground=fg)

    def _on_enter(event):
        colors = theme.get()
        button.configure(
            background=hover_bg or colors["secondary_active"],
            foreground=hover_fg or colors["secondary_fg"],
        )

    def _on_leave(event):
        _apply_base()

    try:
        _apply_base()
        button.configure(activebackground=theme.get()["secondary_active"],
                         activeforeground=theme.get()["secondary_fg"])
    except tk.TclError:
        pass
    button.bind("<Enter>", _on_enter, add="+")
    button.bind("<Leave>", _on_leave, add="+")
    return button


# ── Responsive text and button rows ───────────────────────────


def bind_wrap(label, pad: int = 0, min_width: int = 80):
    """Make a label's wraplength follow its parent's width.

    A fixed wraplength only fits one pane width; in a resizable pane the text
    either clips or leaves a ragged right margin. `pad` is the horizontal
    space the label does not get (its own padx plus the parent's padding).
    """
    parent = label.master

    def _on_resize(event):
        width = event.width - pad
        if width >= min_width:
            label.configure(wraplength=width)

    parent.bind("<Configure>", _on_resize, add="+")


class FlowFrame(ttk.Frame):
    """A row of widgets that wraps onto new lines when the frame is narrow.

    Children are laid out left to right in grid cells; whenever the frame's
    width changes, the row breaks are recomputed from each child's requested
    width, so nothing is ever clipped at the right edge. Add children with
    add() rather than grid()/pack() so the frame owns their placement.
    """

    def __init__(self, parent, gap: int = 6, row_gap: int = 4, **kwargs):
        super().__init__(parent, **kwargs)
        self._items = []
        self._gap = gap
        self._row_gap = row_gap
        self._layout_key = None
        self.bind("<Configure>", self._reflow, add="+")

    def add(self, widget):
        self._items.append(widget)
        self._layout_key = None
        self._reflow()
        return widget

    def _reflow(self, event=None):
        width = event.width if event is not None else self.winfo_width()
        if width <= 1 or not self._items:
            return
        rows, row, used = [], [], 0
        for w in self._items:
            need = w.winfo_reqwidth() + self._gap
            if row and used + need > width:
                rows.append(row)
                row, used = [], 0
            row.append(w)
            used += need
        rows.append(row)
        key = tuple(len(r) for r in rows)
        if key == self._layout_key:
            return
        self._layout_key = key
        for r, items in enumerate(rows):
            for c, w in enumerate(items):
                w.grid(row=r, column=c, padx=(0, self._gap),
                       pady=(0 if r == 0 else self._row_gap, 0), sticky="w")


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
