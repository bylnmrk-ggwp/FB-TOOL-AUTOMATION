"""A full-screen workspace for the accounts themselves.

The Profiles tab is a list built for maintaining a roster - link, rename,
scan, re-login. Reaching one particular account out of forty-nine through it
means scrolling a listbox and reading paths. This window answers a different
question: "open THAT account, now."

Every account is a card in a grid. Typing filters the grid as you type, the
status colour says whether the session is live, and one click opens that
account's real browser window. Nothing here drives Facebook - it hands the
profile to the same launcher the Profiles tab uses, so an account opened
here is an ordinary browser the operator drives themselves.
"""
import tkinter as tk
from tkinter import ttk

from src.storage import config_manager as cfg
from src.ui import theme

# Card geometry, in pixels. Wide enough for an email address at the app's
# normal font without truncation being the common case.
CARD_WIDTH = 230
CARD_HEIGHT = 74
CARD_GAP = 10


class AccountsWorkspace(tk.Toplevel):
    """A window of account cards, one per profile of the selected browser."""

    def __init__(self, parent, on_open, on_refresh_status=None):
        super().__init__(parent)
        self._on_open = on_open
        self._on_refresh_status = on_refresh_status
        self._cards: dict[str, dict] = {}
        self._selected: set[str] = set()
        self._columns = 0          # rebuilt only when the column count changes

        colors = theme.get()
        self.title("Accounts Workspace")
        self.configure(bg=colors["bg"])
        self.geometry("1100x700")
        self.minsize(560, 360)

        self._search_var = tk.StringVar()
        self._count_var = tk.StringVar(value="")
        self._build_ui()
        self.refresh()

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Control-f>", lambda e: self._search_entry.focus_set())
        self._search_entry.focus_set()

    # ── Layout ───────────────────────────────────────────

    def _build_ui(self):
        colors = theme.get()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(bar, text="Accounts", style="Header.TLabel").pack(side="left")
        ttk.Label(bar, textvariable=self._count_var,
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))

        self._open_selected_btn = ttk.Button(
            bar, text="Open selected", command=self._open_selected,
            state="disabled", style="Accent.TButton")
        self._open_selected_btn.pack(side="right")
        ttk.Button(bar, text="Clear selection",
                   command=self._clear_selection).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text="Refresh",
                   command=self.refresh).pack(side="right", padx=(0, 6))

        search_row = ttk.Frame(self)
        search_row.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(search_row, text="Search:").pack(side="left", padx=(0, 6))
        self._search_entry = ttk.Entry(search_row, textvariable=self._search_var)
        self._search_entry.pack(side="left", fill="x", expand=True)
        self._search_var.trace_add("write", lambda *_: self._render())

        # A canvas, because a grid of forty-nine cards has to scroll and Tk
        # frames do not on their own.
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._canvas = tk.Canvas(wrap, bg=colors["canvas_bg"],
                                 highlightthickness=0, borderwidth=0)
        bar_y = ttk.Scrollbar(wrap, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=bar_y.set)
        bar_y.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._grid = ttk.Frame(self._canvas)
        self._grid_id = self._canvas.create_window((0, 0), window=self._grid,
                                                   anchor="nw")
        self._grid.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)

        self._status_var = tk.StringVar(value="Click a card to open that account")
        ttk.Label(self, textvariable=self._status_var,
                  style="Status.TLabel").pack(anchor="w", padx=14, pady=(0, 10))

    def _on_canvas_resize(self, event):
        self._canvas.itemconfigure(self._grid_id, width=event.width)
        columns = max(1, (event.width - CARD_GAP) // (CARD_WIDTH + CARD_GAP))
        if columns != self._columns:
            self._columns = columns
            self._render()

    def _on_wheel(self, event):
        # Only scroll while this window has the pointer: bind_all is global.
        if self.focus_displayof() is None:
            return
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    # ── Data ─────────────────────────────────────────────

    def refresh(self):
        """Reload the account list and its statuses from the database."""
        from src.storage import database as db
        self._accounts = []
        try:
            live = db.logged_in_profiles()
            by_profile = {(a.get("linked_profile") or ""): a
                          for a in db.list_accounts()}
        except Exception as e:
            self._status_var.set(f"Could not read accounts: {e}")
            live, by_profile = set(), {}
        for name in cfg.list_profiles_for_browser():
            account = by_profile.get(name) or {}
            self._accounts.append({
                "profile": name,
                "label": account.get("facebook_name") or account.get("username") or name,
                "username": account.get("username") or "",
                "live": name in live,
                "reason": (account.get("status_reason") or "").strip(),
            })
        self._accounts.sort(key=lambda a: a["label"].lower())
        self._render()

    def _visible(self) -> list[dict]:
        needle = self._search_var.get().strip().lower()
        if not needle:
            return self._accounts
        return [a for a in self._accounts
                if needle in a["label"].lower()
                or needle in a["profile"].lower()
                or needle in a["username"].lower()]

    # ── Cards ────────────────────────────────────────────

    def _render(self):
        for child in self._grid.winfo_children():
            child.destroy()
        self._cards.clear()

        colors = theme.get()
        accounts = self._visible()
        columns = max(1, self._columns or 4)
        for index, account in enumerate(accounts):
            row, column = divmod(index, columns)
            card = tk.Frame(self._grid, bg=colors["card"],
                            highlightthickness=1,
                            highlightbackground=colors["border"],
                            width=CARD_WIDTH, height=CARD_HEIGHT)
            card.grid(row=row, column=column, padx=CARD_GAP // 2,
                      pady=CARD_GAP // 2, sticky="nw")
            card.grid_propagate(False)

            dot = tk.Label(card, text="●", bg=colors["card"],
                           fg=colors["success"] if account["live"] else colors["muted"],
                           font=(theme.UI_FONT, 11))
            dot.place(x=8, y=6)
            name = tk.Label(card, text=account["label"][:26], bg=colors["card"],
                            fg=colors["fg"], font=(theme.UI_FONT, 10, "bold"),
                            anchor="w")
            name.place(x=26, y=6)
            detail = account["username"] or account["profile"]
            sub = tk.Label(card, text=detail[:32], bg=colors["card"],
                           fg=colors["muted"], font=(theme.UI_FONT, 8), anchor="w")
            sub.place(x=26, y=26)
            state = tk.Label(
                card,
                text="logged in" if account["live"]
                else (account["reason"][:26] or "no session recorded"),
                bg=colors["card"],
                fg=colors["success"] if account["live"] else colors["muted"],
                font=(theme.UI_FONT, 8), anchor="w")
            state.place(x=26, y=46)

            self._cards[account["profile"]] = {
                "frame": card, "parts": (dot, name, sub, state),
                "account": account,
            }
            for widget in (card, dot, name, sub, state):
                widget.bind("<Button-1>",
                            lambda e, p=account["profile"]: self._toggle(p))
                widget.bind("<Double-Button-1>",
                            lambda e, p=account["profile"]: self._open_one(p))

        total = len(self._accounts)
        shown = len(accounts)
        self._count_var.set(f"{shown} of {total} shown" if shown != total
                            else f"{total} account(s)")
        self._paint_selection()

    def _toggle(self, profile: str):
        if profile in self._selected:
            self._selected.discard(profile)
        else:
            self._selected.add(profile)
        self._paint_selection()

    def _clear_selection(self):
        self._selected.clear()
        self._paint_selection()

    def _paint_selection(self):
        colors = theme.get()
        for profile, card in self._cards.items():
            chosen = profile in self._selected
            bg = colors["list_select_bg"] if chosen else colors["card"]
            card["frame"].configure(
                bg=bg,
                highlightbackground=colors["accent"] if chosen else colors["border"])
            for part in card["parts"]:
                part.configure(bg=bg)
        count = len(self._selected)
        self._open_selected_btn.config(
            text=f"Open selected ({count})" if count else "Open selected",
            state="normal" if count else "disabled")

    # ── Opening ──────────────────────────────────────────

    def _open_one(self, profile: str):
        self._status_var.set(f"Opening {profile}...")
        try:
            self._on_open(profile)
        except Exception as e:      # noqa: BLE001 - reported here, never raised
            self._status_var.set(f"Could not open {profile}: {e}")

    def _open_selected(self):
        chosen = sorted(self._selected)
        if not chosen:
            return
        self._status_var.set(f"Opening {len(chosen)} account(s)...")
        opened = 0
        for profile in chosen:
            try:
                self._on_open(profile)
                opened += 1
            except Exception:       # noqa: BLE001 - counted, not raised
                pass
        self._status_var.set(f"Opened {opened} of {len(chosen)} account(s)")
