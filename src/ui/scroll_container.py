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
        self.interior.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._window, width=e.width))

        register_wheel_target(self.canvas)

    def apply_theme(self, colors: dict):
        self.canvas.configure(bg=colors["bg"])
