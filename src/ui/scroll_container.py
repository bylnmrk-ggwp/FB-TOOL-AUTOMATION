"""Reusable vertical scroll container.

The one scroll surface for every tall widget stack in the app. It fixes two
things the hand-rolled canvas copies it replaced could not:

* Content shorter than the viewport is stretched to fill it, so a child packed
  with expand=True (a queue list, a profile list) grows with the window
  instead of sitting above blank scroll space. The stretch is a grid minsize
  on a host row, not a pinned canvas-window height: the host keeps requesting
  its natural size, so when content later grows past the viewport the canvas
  still tracks it and nothing is clipped.
* The scrollbar hides when the content fits, so a pane that has nothing to
  scroll does not show a full-height thumb.

Usage:
    wrap = ScrollFrame(parent)
    content = SomeTab(wrap.interior)
    content.pack(fill="both", expand=True)

Pass bg_key="canvas_bg" when the container sits on a card rather than on the
page, so the canvas takes the card's fill.
"""

import tkinter as tk
from tkinter import ttk

from src.ui import theme
from src.ui.effects import register_wheel_target


class ScrollFrame(ttk.Frame):
    def __init__(self, parent, bg_key: str = "bg", **kwargs):
        super().__init__(parent, **kwargs)
        self._bg_key = bg_key
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg=theme.get()[bg_key],
                                highlightthickness=0, borderwidth=0)
        self._vbar = ttk.Scrollbar(self, orient="vertical",
                                   command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self._vbar.grid(row=0, column=1, sticky="ns")
        self._vbar_shown = True

        # host: the canvas window. Its single grid row carries a minsize equal
        # to the viewport height, which is what makes short content fill the
        # pane while tall content still reports its natural height.
        self._host = ttk.Frame(self.canvas)
        self._host.columnconfigure(0, weight=1)
        self._host.rowconfigure(0, weight=1)
        self.interior = ttk.Frame(self._host)
        self.interior.grid(row=0, column=0, sticky="nsew")
        self._window = self.canvas.create_window((0, 0), window=self._host,
                                                 anchor="nw")

        # Recomputing the scrollregion on every <Configure> is quadratic in
        # practice: pinning the host width reflows the host, which fires
        # another host <Configure>, and each pass walks every canvas item via
        # bbox("all"). Showing a large widget stack then costs seconds. Both
        # handlers below collapse a burst of events into one bbox call per
        # idle cycle, and skip the write when nothing moved.
        self._scrollregion_pending = False
        self._last_region = None
        self._last_width = None
        self._last_height = None

        self._host.bind("<Configure>", self._queue_scrollregion)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        register_wheel_target(self.canvas)

    def _queue_scrollregion(self, _event=None):
        if self._scrollregion_pending:
            return
        self._scrollregion_pending = True
        self.after_idle(self._apply_scrollregion)

    def _apply_scrollregion(self):
        self._scrollregion_pending = False
        try:
            region = self.canvas.bbox("all")
        except tk.TclError:
            return  # canvas destroyed while the idle call was queued
        if region and region != self._last_region:
            self._last_region = region
            self.canvas.configure(scrollregion=region)
        self._sync_scrollbar(region)

    def _sync_scrollbar(self, region):
        """Show the bar only when the content is taller than the viewport."""
        try:
            viewport = self.canvas.winfo_height()
        except tk.TclError:
            return
        content = (region[3] - region[1]) if region else 0
        need = content > viewport + 1
        if need and not self._vbar_shown:
            self._vbar.grid()
            self._vbar_shown = True
        elif not need and self._vbar_shown:
            self._vbar.grid_remove()
            self._vbar_shown = False

    def _on_canvas_configure(self, event):
        if event.width != self._last_width:
            self._last_width = event.width
            self.canvas.itemconfigure(self._window, width=event.width)
        if event.height != self._last_height:
            self._last_height = event.height
            self._host.rowconfigure(0, minsize=event.height)

    def apply_theme(self, colors: dict):
        self.canvas.configure(bg=colors[self._bg_key])
