"""Reusable vertical scroll container.

Wraps the canvas + scrollbar + interior-width-pinning pattern already
used by QueueTab and ShareTab so any tall widget stack (e.g. ProfilesTab
inside a narrow pane) can scroll when its pane is shorter than its
natural height.

Usage:
    wrap = ScrollFrame(parent)
    content = SomeTab(wrap.interior)
    content.pack(fill="both", expand=True)
"""

import tkinter as tk
from tkinter import ttk

from src.ui import theme
from src.ui.effects import register_wheel_target


class ScrollFrame(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg=theme.get()["bg"],
                                highlightthickness=0, borderwidth=0)
        self._vbar = ttk.Scrollbar(self, orient="vertical",
                                   command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self._vbar.grid(row=0, column=1, sticky="ns")

        self.interior = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.interior,
                                                 anchor="nw")

        # Recomputing the scrollregion on every <Configure> is quadratic in
        # practice: pinning the interior width reflows the interior, which
        # fires another interior <Configure>, and each pass walks every canvas
        # item via bbox("all"). Showing a large widget stack then costs
        # seconds. Both handlers below collapse a burst of events into one
        # bbox call per idle cycle, and skip the write when nothing moved.
        self._scrollregion_pending = False
        self._last_region = None
        self._last_width = None

        self.interior.bind("<Configure>", self._queue_scrollregion)
        self.canvas.bind("<Configure>", self._pin_interior_width)

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

    def _pin_interior_width(self, event):
        if event.width == self._last_width:
            return
        self._last_width = event.width
        self.canvas.itemconfigure(self._window, width=event.width)

    def apply_theme(self, colors: dict):
        self.canvas.configure(bg=colors["bg"])
