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
        # Before the frame is mapped winfo_width() is 1, so fall back to the
        # configured width; int() because cget may hand back a Tcl string.
        start = (self.winfo_width() if self.winfo_width() > 1
                 else int(self.cget("width")))
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
        # winfo_manager(), not winfo_ismapped(): a label packed under a
        # withdrawn or not-yet-mapped window reports unmapped, which would
        # leave every label packed while collapsed.
        for p in self._parts.values():
            packed = p["label"].winfo_manager() == "pack"
            if show and not packed:
                p["label"].pack(side="left", fill="x", expand=True)
            elif not show and packed:
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
