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

Returns a `clear()` callable for listboxes — call it from apply_theme()
after re-theming, or after repopulating the listbox contents.
"""

import time
import tkinter as tk

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
