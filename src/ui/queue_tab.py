import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from src.storage import config_manager as cfg
from src.ui import theme
from src.ui.effects import attach_listbox_hover, bind_wrap

SAVED_FILE = Path.home() / ".autoshare" / "saved_shares.json"

COMMENT_PLACEHOLDER = "profile1 - nice!\nprofile2 - good!"
ONECOMMENT_URLS_PLACEHOLDER = ("https://www.facebook.com/username/posts/111\n"
                               "https://www.facebook.com/username/posts/222")
ONECOMMENT_COMMENT_PLACEHOLDER = ("Great post! Keep sharing.\n"
                                  "Nice one, thanks for this.")


class QueueTab(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self._items: list[dict] = []
        self._on_run_queue_cb = None
        self._on_stop_queue_cb = None
        self._on_watch_url_cb = None
        self._on_stop_watch_cb = None
        # Track login status per profile: profile_name → True (logged in) / False (not) / None (unknown)
        self._profile_status: dict[str, bool | None] = {}
        self._rate_limited_profiles: set[str] = set()
        # Kept for the live run: a queue run marks each profile as it goes.

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=10, pady=10)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)

        # Scrollable surface for tall content. ScrollFrame stretches short
        # content to the viewport, so the queue list below can grow with the
        # window, and hides its bar when nothing scrolls.
        from src.ui.scroll_container import ScrollFrame
        self._scroll = ScrollFrame(card, bg_key="canvas_bg")
        self._scroll.grid(row=0, column=0, sticky="nsew")
        self._canvas = self._scroll.canvas

        # Inner frame with padding so content doesn't touch canvas edges
        inner = ttk.Frame(self._scroll.interior)
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        ttk.Label(inner, text="Share Queue",
                  style="Header.TLabel").pack(anchor="w", **pad)
        intro = ttk.Label(inner, text="Load saved presets or add timeline shares — each item uses its own profile.",
                          foreground=theme.get()["muted"])
        intro.pack(anchor="w", **pad)
        bind_wrap(intro, pad=2 * pad["padx"])

        # ── Profiles ──────────────────────────────────────
        # A dot per profile used to sit here. At 400+ profiles it was a wall
        # of names nobody read, and it cost a full relayout every time one
        # logged in. How many profiles this browser has is the whole answer.
        status_header = ttk.Frame(inner)
        status_header.pack(fill="x", **pad)
        self._active_count_var = tk.StringVar(value="")
        ttk.Label(status_header, textvariable=self._active_count_var,
                  style="Heading.TLabel").pack(side="left")

        ttk.Separator(inner, orient="horizontal").pack(fill="x", **pad)

        # ── Quick add: unified form (radio-selected command) ──
        add_label = ttk.Label(inner, text="Quick Add — All Profiles",
                              style="Heading.TLabel")
        add_label.pack(anchor="w", **pad)
        add_hint = ttk.Label(inner, text="Choose a command, fill in the form, then add it to the queue.",
                             foreground=theme.get()["muted"])
        add_hint.pack(anchor="w", **pad)
        bind_wrap(add_hint, pad=2 * pad["padx"])

        self._quick_mode_var = tk.StringVar(value="timeline")
        mode_row = ttk.Frame(inner)
        mode_row.pack(fill="x", **pad)
        for value, text in (
            ("timeline", "Timeline Share"),
            ("features", "Post Features"),
            ("onecomment", "Comment All URLs — All Accounts"),
        ):
            ttk.Radiobutton(mode_row, text=text, value=value,
                            variable=self._quick_mode_var,
                            command=self._on_quick_mode_change).pack(
                                side="left", padx=(0, 14))

        ttk.Separator(inner, orient="horizontal").pack(fill="x", **pad)

        self._quick_forms: dict[str, ttk.Frame] = {}
        form_container = ttk.Frame(inner)
        form_container.pack(fill="x", **pad)
        form_container.columnconfigure(0, weight=1)

        # ── Mode: Timeline Share (all profiles) ──
        timeline_form = ttk.Frame(form_container)
        timeline_form.columnconfigure(1, weight=1)
        timeline_form.grid(row=0, column=0, sticky="nsew")
        self._quick_forms["timeline"] = timeline_form

        ttk.Label(timeline_form, text="Post URL:").grid(row=0, column=0, padx=(0, 6), sticky="w")
        self._timeline_url_var = tk.StringVar()
        timeline_entry = ttk.Entry(timeline_form, textvariable=self._timeline_url_var)
        timeline_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 6))
        timeline_entry.bind("<Return>", lambda e: self._on_add_timeline())

        self.add_timeline_btn = ttk.Button(timeline_form, text="Add to Queue (All Profiles)",
                                           command=self._on_add_timeline,
                                           state="disabled", style="Accent.TButton")
        self.add_timeline_btn.grid(row=0, column=3, sticky="e")

        ttk.Label(timeline_form, text="Comment:").grid(row=1, column=0, padx=(0, 6), pady=(6, 0), sticky="w")
        self._timeline_comment_var = tk.StringVar()
        comment_entry = ttk.Entry(timeline_form, textvariable=self._timeline_comment_var)
        comment_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 6), pady=(6, 0))
        comment_entry.bind("<Return>", lambda e: self._on_add_timeline())

        ttk.Label(timeline_form, text="Reaction:").grid(row=2, column=0, padx=(0, 6), pady=(6, 0), sticky="w")
        self._timeline_reaction_var = tk.StringVar(value="none")
        self._timeline_reaction_dropdown = ttk.Combobox(
            timeline_form, textvariable=self._timeline_reaction_var,
            values=["none", "like", "love", "care", "haha", "wow", "sad", "angry"],
            state="readonly", width=10)
        self._timeline_reaction_dropdown.grid(row=2, column=1, sticky="w", pady=(6, 0))

        self._timeline_react_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(timeline_form, text="React only (no share)",
                        variable=self._timeline_react_only_var,
                        command=self._update_timeline_btn).grid(
            row=3, column=1, sticky="w", pady=(6, 0))

        self._timeline_url_var.trace_add("write", self._update_timeline_btn)
        timeline_form.grid_remove()

        # ── Mode: Post Features (all profiles) ──
        features_form = ttk.Frame(form_container)
        features_form.columnconfigure(1, weight=1)
        features_form.grid(row=0, column=0, sticky="nsew")
        self._quick_forms["features"] = features_form

        ttk.Label(features_form, text="Post URL:").grid(row=0, column=0, padx=(0, 6), sticky="w")
        self._features_url_var = tk.StringVar()
        features_url_entry = ttk.Entry(features_form, textvariable=self._features_url_var)
        features_url_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 6))
        features_url_entry.bind("<Return>", lambda e: self._on_add_features())

        self.add_features_btn = ttk.Button(features_form, text="Add to Queue (All Profiles)",
                                           command=self._on_add_features, state="disabled",
                                           style="Accent.TButton")
        self.add_features_btn.grid(row=0, column=3, sticky="e")

        self._feat_comment_var = tk.BooleanVar(value=False)
        self._feat_share_var = tk.BooleanVar(value=False)
        self._feat_story_var = tk.BooleanVar(value=False)
        self._feat_react_var = tk.BooleanVar(value=False)
        # Watch runs after the others and does not close: the profiles stay on
        # the post playing the live, which is what counts as a viewer.
        self._feat_watch_var = tk.BooleanVar(value=False)

        feat_row = ttk.Frame(features_form)
        feat_row.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(feat_row, text="Comment", variable=self._feat_comment_var,
                        command=self._update_features_btn).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(feat_row, text="Share to Timeline", variable=self._feat_share_var,
                        command=self._update_features_btn).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(feat_row, text="Share to Story", variable=self._feat_story_var,
                        command=self._update_features_btn).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(feat_row, text="React", variable=self._feat_react_var,
                        command=self._update_features_btn).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(feat_row, text="Watch Live (stay on post)",
                        variable=self._feat_watch_var,
                        command=self._update_features_btn).pack(side="left", padx=(0, 10))
        ttk.Label(feat_row, text="mins:").pack(side="left", padx=(6, 2))
        self._feat_watch_minutes_var = tk.StringVar(value="")
        ttk.Entry(feat_row, textvariable=self._feat_watch_minutes_var,
                  width=5).pack(side="left")
        ttk.Label(feat_row, text="(blank = whole live, start to end)",
                  foreground=theme.get()["muted"]).pack(side="left", padx=(4, 0))

        ttk.Label(features_form, text="Comment (name - text per profile):").grid(row=2, column=0, padx=(0, 6), pady=(6, 0), sticky="nw")
        self._features_comment_text = tk.Text(features_form, height=2, width=30, wrap="word")
        self._features_comment_text.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(0, 6), pady=(6, 0))

        def _add_feat_comment_placeholder(event=None):
            from src.ui import theme
            if not self._features_comment_text.get("1.0", tk.END).strip():
                self._features_comment_text.insert("1.0", COMMENT_PLACEHOLDER)
                self._features_comment_text.config(foreground=theme.get()["placeholder"])

        def _remove_feat_comment_placeholder(event):
            from src.ui import theme
            content = self._features_comment_text.get("1.0", tk.END).strip()
            if content == COMMENT_PLACEHOLDER:
                self._features_comment_text.delete("1.0", tk.END)
                self._features_comment_text.config(foreground=theme.get()["input_fg"])

        self._features_comment_text.bind("<FocusIn>", _remove_feat_comment_placeholder)
        self._features_comment_text.bind("<FocusOut>", _add_feat_comment_placeholder)
        _add_feat_comment_placeholder()
        self._features_comment_text.bind("<KeyRelease>", self._update_features_btn)

        ttk.Label(features_form, text="Reaction:").grid(row=3, column=0, padx=(0, 6), pady=(6, 0))
        self._features_reaction_var = tk.StringVar(value="like")
        ttk.Combobox(features_form, textvariable=self._features_reaction_var,
                     values=["like", "love", "care", "haha", "wow", "sad", "angry"],
                     state="readonly", width=10).grid(row=3, column=1, sticky="w", pady=(6, 0))

        self._features_url_var.trace_add("write", self._update_features_btn)
        features_form.grid_remove()

        # ── Mode: Comment All URLs (all accounts) ──
        onecomment_form = ttk.Frame(form_container)
        onecomment_form.columnconfigure(1, weight=1)
        onecomment_form.grid(row=0, column=0, sticky="nsew")
        self._quick_forms["onecomment"] = onecomment_form

        ttk.Label(onecomment_form, text="Post URLs (one per line):").grid(row=0, column=0, padx=(0, 6), sticky="nw")
        oc_urls_frame = ttk.Frame(onecomment_form)
        oc_urls_frame.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(0, 6))
        oc_urls_frame.columnconfigure(0, weight=1)
        oc_urls_frame.rowconfigure(0, weight=1)

        self._onecomment_urls_text = tk.Text(oc_urls_frame, height=4,
                                             font=(theme.MONO_FONT, 9), wrap="word",
                                             borderwidth=1, relief="solid",
                                             highlightthickness=1,
                                             highlightbackground=theme.get()["border"])
        oc_urls_scroll = ttk.Scrollbar(oc_urls_frame, orient="vertical",
                                       command=self._onecomment_urls_text.yview)
        self._onecomment_urls_text.config(yscrollcommand=oc_urls_scroll.set)
        self._onecomment_urls_text.grid(row=0, column=0, sticky="nsew")
        oc_urls_scroll.grid(row=0, column=1, sticky="ns")

        def _add_onecomment_urls_placeholder(event=None):
            from src.ui import theme
            if not self._onecomment_urls_text.get("1.0", tk.END).strip():
                self._onecomment_urls_text.insert("1.0", ONECOMMENT_URLS_PLACEHOLDER)
                self._onecomment_urls_text.config(foreground=theme.get()["placeholder"])

        def _remove_onecomment_urls_placeholder(event):
            from src.ui import theme
            content = self._onecomment_urls_text.get("1.0", tk.END).strip()
            if content == ONECOMMENT_URLS_PLACEHOLDER:
                self._onecomment_urls_text.delete("1.0", tk.END)
                self._onecomment_urls_text.config(foreground=theme.get()["input_fg"])

        self._onecomment_urls_text.bind("<FocusIn>", _remove_onecomment_urls_placeholder)
        self._onecomment_urls_text.bind("<FocusOut>", _add_onecomment_urls_placeholder)
        _add_onecomment_urls_placeholder()

        ttk.Label(onecomment_form, text="Comments (one per line):").grid(row=1, column=0, padx=(0, 6), pady=(6, 0), sticky="nw")
        oc_comment_frame = ttk.Frame(onecomment_form)
        oc_comment_frame.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(0, 6), pady=(6, 0))
        oc_comment_frame.columnconfigure(0, weight=1)
        oc_comment_frame.rowconfigure(0, weight=1)

        self._onecomment_comment_text = tk.Text(oc_comment_frame, height=2,
                                                font=(theme.UI_FONT, 10), wrap="word",
                                                borderwidth=1, relief="solid",
                                                highlightthickness=1,
                                                highlightbackground=theme.get()["border"])
        oc_comment_scroll = ttk.Scrollbar(oc_comment_frame, orient="vertical",
                                          command=self._onecomment_comment_text.yview)
        self._onecomment_comment_text.config(yscrollcommand=oc_comment_scroll.set)
        self._onecomment_comment_text.grid(row=0, column=0, sticky="nsew")
        oc_comment_scroll.grid(row=0, column=1, sticky="ns")

        def _add_onecomment_comment_placeholder(event=None):
            from src.ui import theme
            if not self._onecomment_comment_text.get("1.0", tk.END).strip():
                self._onecomment_comment_text.insert("1.0", ONECOMMENT_COMMENT_PLACEHOLDER)
                self._onecomment_comment_text.config(foreground=theme.get()["placeholder"])

        def _remove_onecomment_comment_placeholder(event):
            from src.ui import theme
            content = self._onecomment_comment_text.get("1.0", tk.END).strip()
            if content == ONECOMMENT_COMMENT_PLACEHOLDER:
                self._onecomment_comment_text.delete("1.0", tk.END)
                self._onecomment_comment_text.config(foreground=theme.get()["input_fg"])

        self._onecomment_comment_text.bind("<FocusIn>", _remove_onecomment_comment_placeholder)
        self._onecomment_comment_text.bind("<FocusOut>", _add_onecomment_comment_placeholder)
        _add_onecomment_comment_placeholder()

        self._onecomment_btn = ttk.Button(onecomment_form,
                                          text="Add to Queue (All URLs × All Accounts)",
                                          command=self._on_add_one_comment_each,
                                          state="disabled", style="Accent.TButton")
        self._onecomment_btn.grid(row=2, column=1, columnspan=3, sticky="ew",
                                  padx=(0, 6), pady=(6, 0))

        self._onecomment_urls_text.bind("<KeyRelease>", self._update_onecomment_btn)
        self._onecomment_comment_text.bind("<KeyRelease>", self._update_onecomment_btn)
        onecomment_form.grid_remove()

        self._on_quick_mode_change()

        ttk.Separator(inner, orient="horizontal").pack(fill="x", **pad)

        # ── Quick add: text post ─────────────────────────
        text_label = ttk.Label(inner, text="Post Text to Timeline",
                              style="Heading.TLabel")
        text_label.pack(anchor="w", **pad)

        text_frame = ttk.Frame(inner)
        text_frame.pack(fill="x", **pad)
        text_frame.columnconfigure(1, weight=1)

        # Row 0: Text content (multiline)
        ttk.Label(text_frame, text="Content:").grid(row=0, column=0, padx=(0, 6), sticky="nw")
        text_entry_frame = ttk.Frame(text_frame)
        text_entry_frame.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(0, 6))
        text_entry_frame.columnconfigure(0, weight=1)
        text_entry_frame.rowconfigure(0, weight=1)

        self._text_content_widget = tk.Text(text_entry_frame, height=3,
                                            font=(theme.UI_FONT, 10),
                                            borderwidth=0,
                                            highlightthickness=1,
                                            highlightbackground=theme.get()["border"],
                                            wrap="word")
        text_scroll = ttk.Scrollbar(text_entry_frame, orient="vertical",
                                    command=self._text_content_widget.yview)
        self._text_content_widget.config(yscrollcommand=text_scroll.set)
        self._text_content_widget.grid(row=0, column=0, sticky="nsew")
        text_scroll.grid(row=0, column=1, sticky="ns")

        self._text_content_widget.bind("<KeyRelease>", self._update_text_btn)
        self._text_content_widget.bind("<Control-Return>", lambda e: self._on_add_text_post())

        # Row 1: Images (multi-select listbox + Add/Remove)
        self._text_image_paths: list[str] = []

        ttk.Label(text_frame, text="Images:").grid(row=1, column=0, padx=(0, 6), pady=(6, 0), sticky="nw")

        img_frame = ttk.Frame(text_frame)
        img_frame.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(0, 6), pady=(6, 0))
        img_frame.columnconfigure(0, weight=1)

        self._text_image_listbox = tk.Listbox(img_frame, height=3, font=(theme.MONO_FONT, 9),
                                               borderwidth=0, highlightthickness=1,
                                               highlightbackground=theme.get()["border"],
                                               activestyle="none", selectmode="extended")
        self._text_image_listbox.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self._clear_image_hover = attach_listbox_hover(self._text_image_listbox)

        img_btn_frame = ttk.Frame(img_frame)
        img_btn_frame.grid(row=0, column=1, sticky="ne", padx=(6, 0), pady=(0, 4))

        ttk.Button(img_btn_frame, text="+ Add",
                   command=self._on_browse_images).pack(side="top", pady=(0, 2))
        ttk.Button(img_btn_frame, text="Remove",
                   command=self._on_remove_image).pack(side="top")

        # Row 2: Post to All Profiles button
        ttk.Label(text_frame, text="").grid(row=2, column=0)  # spacer

        self.add_text_all_btn = ttk.Button(text_frame, text="Post to All Profiles",
                                            command=self._on_add_text_post,
                                            state="disabled", style="Accent.TButton")
        self.add_text_all_btn.grid(row=2, column=1, columnspan=3, sticky="ew",
                                   padx=(0, 0), pady=(6, 0))

        ttk.Separator(inner, orient="horizontal").pack(fill="x", **pad)

        # Queue list
        list_frame = ttk.Frame(inner)
        list_frame.pack(fill="both", expand=True, **pad)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        self.queue_listbox = tk.Listbox(
            list_frame, height=8, yscrollcommand=scrollbar.set,
            font=(theme.MONO_FONT, 9), borderwidth=0,
            highlightthickness=1, highlightbackground=theme.get()["border"],
            activestyle="none")
        scrollbar.config(command=self.queue_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.queue_listbox.grid(row=0, column=0, sticky="nsew")
        self.queue_listbox.bind("<<ListboxSelect>>", self._on_select)
        self._clear_queue_hover = attach_listbox_hover(self.queue_listbox)

        # Buttons — use grid so they wrap naturally
        btn_frame = ttk.Frame(inner)
        btn_frame.pack(fill="x", **pad)
        btn_frame.columnconfigure(3, weight=1)

        self.load_btn = ttk.Button(btn_frame, text="Load All Presets",
                                   command=self._on_load_presets)
        self.load_btn.grid(row=0, column=0, padx=(0, 6), pady=2)

        self.remove_btn = ttk.Button(btn_frame, text="Remove Item",
                                     command=self._on_remove, state="disabled")
        self.remove_btn.grid(row=0, column=1, padx=(0, 6), pady=2)

        self.clear_btn = ttk.Button(btn_frame, text="Clear All",
                                    command=self._on_clear, state="disabled")
        self.clear_btn.grid(row=0, column=2, padx=(0, 6), pady=2)

        self.run_btn = ttk.Button(btn_frame, text="Start Queue",
                                  command=self._on_run, state="disabled",
                                  style="Accent.TButton")
        self.run_btn.grid(row=0, column=3, padx=(6, 0), pady=2, sticky="e")

        # Only usable while a run is going: a queue that has started is
        # otherwise unstoppable short of closing the app.
        self.stop_btn = ttk.Button(btn_frame, text="Stop Queue",
                                   command=self._on_stop_queue, state="disabled")
        self.stop_btn.grid(row=0, column=4, padx=(6, 0), pady=2, sticky="e")

        # ── Live watch: open every active profile on a pasted URL ─────
        watch_frame = ttk.Frame(inner)
        watch_frame.pack(fill="x", **pad)
        ttk.Label(watch_frame, text="Watch URL:").pack(side="left")
        self._watch_url_var = tk.StringVar()
        watch_entry = ttk.Entry(watch_frame, textvariable=self._watch_url_var)
        watch_entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.stop_watch_btn = ttk.Button(watch_frame, text="Stop",
                                         command=self._on_stop_watch)
        self.stop_watch_btn.pack(side="right")
        self.watch_btn = ttk.Button(watch_frame, text="Watch (active profiles)",
                                    command=self._on_watch,
                                    style="Accent.TButton")
        self.watch_btn.pack(side="right", padx=(0, 6))
        # How long the watch runs. Blank means "until Stop", which is what the
        # button did before this field existed.
        ttk.Label(watch_frame, text="min").pack(side="right", padx=(4, 10))
        self._watch_minutes_var = tk.StringVar(
            value=str(cfg.get_setting("watch_minutes", 120)))
        ttk.Entry(watch_frame, textvariable=self._watch_minutes_var,
                  width=5).pack(side="right")
        ttk.Label(watch_frame, text="for").pack(side="right", padx=(8, 4))

        # ── Browser render mode ───────────────────────────
        # Facebook serves a stripped page to the legacy headless engine, so
        # comments can't find the composer. "Hidden (recommended)" uses the
        # new headless engine (renders like real Chrome, no windows);
        # "Visible windows" is the guaranteed fallback.
        mode_frame = ttk.Frame(inner)
        mode_frame.pack(fill="x", **pad)
        ttk.Label(mode_frame, text="Browser mode:",
                  style="Heading.TLabel").pack(side="left", padx=(0, 8))
        self._browser_mode_var = tk.StringVar(
            value=cfg.get_setting("browser_mode", "headless_new"))
        self._browser_mode_labels = {
            "headless_new": "Hidden (recommended)",
            "visible": "Visible windows",
            "headless": "Legacy (lowest RAM)",
        }
        self._browser_mode_combo = ttk.Combobox(
            mode_frame, state="readonly", width=22,
            values=list(self._browser_mode_labels.values()))
        self._browser_mode_combo.set(
            self._browser_mode_labels.get(
                self._browser_mode_var.get(), "Hidden (recommended)"))
        self._browser_mode_combo.pack(side="left")
        self._browser_mode_combo.bind(
            "<<ComboboxSelected>>", self._on_browser_mode_change)

        # Progress / Status
        status_frame = ttk.Frame(inner)
        status_frame.pack(fill="x", **pad)

        self.progress = ttk.Progressbar(status_frame, mode="determinate")
        self.progress.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var,
                  style="Status.TLabel").pack(side="left")

    def _on_browser_mode_change(self, event=None):
        """Persist the chosen browser render mode to config."""
        label = self._browser_mode_combo.get()
        value = next((k for k, v in self._browser_mode_labels.items()
                      if v == label), "headless_new")
        cfg.save_setting("browser_mode", value)
        self.set_status(f"Browser mode set to '{label}' — applies next run.")

    # ── Public API ───────────────────────────────────────────

    @property
    def items(self):
        return list(self._items)

    def set_on_run_queue(self, callback):
        self._on_run_queue_cb = callback

    def set_on_stop_queue(self, callback):
        """callback() - end the run after the item currently in flight."""
        self._on_stop_queue_cb = callback

    def _on_stop_queue(self):
        """Ask the worker to stop, and say so rather than looking frozen.

        The button goes disabled straight away: the run does not end on the
        click, it ends when the action in flight finishes, and a button that
        still looks pressable invites a second press.
        """
        self.stop_btn.config(state="disabled")
        self.set_status("Stopping after the current item...")
        callback = getattr(self, "_on_stop_queue_cb", None)
        if callback:
            callback()

    def set_on_watch_url(self, callback):
        self._on_watch_url_cb = callback

    def set_on_stop_watch(self, callback):
        self._on_stop_watch_cb = callback

    def _on_watch(self):
        url = self._watch_url_var.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("Invalid URL",
                                 "Watch URL must start with http:// or https://")
            return
        raw = self._watch_minutes_var.get().strip()
        minutes = None
        if raw:
            try:
                minutes = float(raw)
            except ValueError:
                messagebox.showerror("Invalid duration",
                                     "Watch duration must be a number of "
                                     "minutes, or blank to run until Stop.")
                return
            if minutes <= 0:
                messagebox.showerror("Invalid duration",
                                     "Watch duration must be greater than 0.")
                return
            cfg.save_setting("watch_minutes", minutes)
        if self._on_watch_url_cb:
            self._on_watch_url_cb(url, minutes)

    def _on_stop_watch(self):
        if self._on_stop_watch_cb:
            self._on_stop_watch_cb()

    def set_status(self, text: str):
        self.status_var.set(text)

    def apply_theme(self, colors: dict):
        """Re-theme raw-tk widgets that aren't driven by ttk styles."""
        self._canvas.configure(bg=colors["canvas_bg"])

        list_widgets = [self.queue_listbox, self._text_image_listbox]
        for w in list_widgets:
            w.configure(bg=colors["list_bg"], fg=colors["list_fg"],
                        selectbackground=colors["list_select_bg"],
                        selectforeground=colors["list_select_fg"],
                        highlightbackground=colors["border"],
                        highlightcolor=colors["accent"])

        text_widgets = [self._text_content_widget, self._features_comment_text,
                        self._onecomment_urls_text, self._onecomment_comment_text]
        for w in text_widgets:
            w.configure(bg=colors["input_bg"], fg=colors["input_fg"],
                        highlightbackground=colors["border"],
                        highlightcolor=colors["accent"])

        if hasattr(self, "_clear_queue_hover"):
            self._clear_queue_hover()
        if hasattr(self, "_clear_image_hover"):
            self._clear_image_hover()

        # Comment box keeps placeholder styling while placeholder text is shown
        if self._features_comment_text.get("1.0", tk.END).strip() == COMMENT_PLACEHOLDER:
            self._features_comment_text.config(foreground=colors["placeholder"])
        else:
            self._features_comment_text.config(foreground=colors["input_fg"])

        # One-comment-per-profile boxes keep placeholder styling too
        if self._onecomment_urls_text.get("1.0", tk.END).strip() == ONECOMMENT_URLS_PLACEHOLDER:
            self._onecomment_urls_text.config(foreground=colors["placeholder"])
        else:
            self._onecomment_urls_text.config(foreground=colors["input_fg"])
        if self._onecomment_comment_text.get("1.0", tk.END).strip() == ONECOMMENT_COMMENT_PLACEHOLDER:
            self._onecomment_comment_text.config(foreground=colors["placeholder"])
        else:
            self._onecomment_comment_text.config(foreground=colors["input_fg"])

        self._refresh_profile_status()

    def refresh_profiles(self):
        """Rebuild profile status display."""
        self._refresh_profile_status()



    def update_profile_status(self, profile_name: str, logged_in: bool):
        """Update login status for a profile and refresh the display."""
        self._profile_status[profile_name] = logged_in
        self._refresh_profile_status()

    def mark_profile_rate_limited(self, profile_name: str):
        """Mark a profile as rate-limited — shows orange dot."""
        self._rate_limited_profiles.add(profile_name)
        self._refresh_profile_status()


    def _refresh_profile_status(self):
        """Say how many profiles the selected browser has.

        No login state: reading it meant a database query on every refresh -
        and a refresh runs per profile during a login scan - to answer a
        question the Check Login Status button already answers on demand.
        """
        from src.core import browser_choice

        profiles = cfg.list_profiles_for_browser()
        browser = browser_choice.current_browser().title()
        self._active_count_var.set(
            f"{len(profiles)} {browser} profile(s)" if profiles
            else f"No {browser} profiles saved")

    def set_running(self, running: bool):
        state = "disabled" if running else "normal"
        self.load_btn.config(state=state)
        self.remove_btn.config(state=state)
        self.clear_btn.config(state=state)
        self.run_btn.config(state="disabled" if running else
                            ("normal" if self._items else "disabled"))
        self.stop_btn.config(state="normal" if running else "disabled")

    def update_progress(self, current: int, total: int):
        if total > 0:
            self.progress["value"] = (current / total) * 100
            self.progress["maximum"] = 100
        else:
            self.progress["value"] = 0

    def clear_all(self):
        self._items.clear()
        self._refresh()
        self._update_buttons()

    # ── Internal ─────────────────────────────────────────────

    def _refresh(self):
        if hasattr(self, "_clear_queue_hover"):
            self._clear_queue_hover()
        self.queue_listbox.delete(0, "end")
        for i, item in enumerate(self._items):
            profile = item["profile_name"]
            action_type = item.get("action_type", "group")
            rxn = item.get("reaction") or ""

            if action_type == "post_text":
                text = item.get("text", "")[:60]
                image_count = len(item.get("image_paths") or [])
                img_tag = f" 📷x{image_count}" if image_count > 1 else (" 📷" if image_count == 1 else "")
                line = f"{i+1}. [{profile}] Text Post{img_tag} | {text}"
            elif action_type == "react":
                rxn = item.get("reaction", "like")
                line = f"{i+1}. [{profile}] React: {rxn:<12} | {item['post_url']}"
            elif action_type == "comment":
                url = item['post_url']
                cmt = (item.get("comment_text", "") or "").replace("\n", " ")
                cmt = f'  ("{cmt[:25]}"...)' if len(cmt) > 25 else (
                    f'  ("{cmt}")' if cmt else "")
                line = f"{i+1}. [{profile}] Comment | {url}{cmt}"
            elif action_type == "share":
                line = f"{i+1}. [{profile}] Share to Timeline | {item['post_url']}"
            elif action_type == "story":
                line = f"{i+1}. [{profile}] Share to Story     | {item['post_url']}"
            else:
                url = item["post_url"]
                cmt = item.get("comment_text") or item.get("comment") or ""
                tags = []
                if rxn:
                    tags.append(rxn)
                if cmt:
                    tags.append("cmt")
                tag_str = f" [{','.join(tags)}]" if tags else ""

                is_timeline = action_type == "timeline"
                target = "Timeline" if is_timeline else item.get("group_name", "?")
                line = f"{i+1}. [{profile}] {target:<20}{tag_str} | {url}"

            self.queue_listbox.insert("end", line)

    def _on_quick_mode_change(self):
        selected = self._quick_mode_var.get()
        for name, form in self._quick_forms.items():
            if name == selected:
                form.grid()
            else:
                form.grid_remove()
        self.after_idle(lambda: self._canvas.yview_moveto(0))

    def _update_timeline_btn(self, *_):
        ready = bool(self._timeline_url_var.get().strip())
        self.add_timeline_btn.config(state="normal" if ready else "disabled")

    def _update_features_btn(self, *_):
        url = self._features_url_var.get().strip()
        has_feature = any([
            self._feat_comment_var.get(),
            self._feat_share_var.get(),
            self._feat_story_var.get(),
            self._feat_react_var.get(),
            self._feat_watch_var.get(),
        ])
        ready = bool(url and has_feature)
        if self._feat_comment_var.get():
            comment = self._features_comment_text.get("1.0", tk.END).strip()
            if not comment or comment == COMMENT_PLACEHOLDER:
                ready = False
        self.add_features_btn.config(state="normal" if ready else "disabled")

    def _update_text_btn(self, *_):
        text = self._text_content_widget.get("1.0", "end-1c").strip()
        ready = bool(text)
        self.add_text_all_btn.config(state="normal" if ready else "disabled")

    def _on_browse_images(self):
        """Open a file dialog to select one or more images."""
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")],
        )
        for p in paths:
            if p not in self._text_image_paths:
                self._text_image_paths.append(p)
                self._text_image_listbox.insert("end", Path(p).name)
        

    def _on_remove_image(self):
        """Remove selected images from the list."""
        sel = self._text_image_listbox.curselection()
        for i in reversed(sel):
            self._text_image_listbox.delete(i)
            del self._text_image_paths[i]
        if hasattr(self, "_clear_image_hover"):
            self._clear_image_hover()

    def _on_add_text_post(self):
        text = self._text_content_widget.get("1.0", "end-1c").strip()
        if not text:
            return
        profiles = cfg.list_profiles_for_browser()
        if not profiles:
            messagebox.showinfo("No Profiles", "No saved profiles found.")
            return
        image_paths = list(self._text_image_paths) if self._text_image_paths else None

        count = 0
        for profile_name in profiles:
            self._items.append({
                "action_type": "post_text",
                "profile_name": profile_name,
                "text": text,
                "image_paths": image_paths,
            })
            count += 1
        self._text_content_widget.delete("1.0", "end")
        self._text_image_paths.clear()
        if hasattr(self, "_clear_image_hover"):
            self._clear_image_hover()
        self._text_image_listbox.delete(0, "end")
        self._update_text_btn()
        self._refresh()
        self._update_buttons()
        self.set_status(f"Added text post for {count} profile(s): {text[:40]}...")

    def _on_add_timeline(self):
        url = self._timeline_url_var.get().strip()
        if not url:
            return
        
        # Validate URL format
        if not url.startswith("http"):
            messagebox.showerror("Invalid URL", "Post URL must start with http:// or https://")
            return
        
        profiles = cfg.list_profiles_for_browser()
        if not profiles:
            messagebox.showinfo("No Profiles", "No saved profiles found.")
            return
        comment = self._timeline_comment_var.get().strip()
        reaction_raw = self._timeline_reaction_var.get().strip().lower()
        reaction = "" if reaction_raw == "none" else reaction_raw
        react_only = self._timeline_react_only_var.get()
        if react_only and not reaction:
            messagebox.showwarning(
                "No Reaction",
                "React-only mode needs a Reaction selected.\n"
                "Pick one from the Reaction dropdown, or uncheck 'React only'.")
            return
        count = 0
        for profile_name in profiles:
            if react_only:
                if not reaction:
                    continue
                self._items.append({
                    "action_type": "react",
                    "profile_name": profile_name,
                    "post_url": url,
                    "reaction": reaction,
                })
            else:
                self._items.append({
                    "action_type": "timeline",
                    "profile_name": profile_name,
                    "post_url": url,
                    "comment_text": comment,
                    "reaction": reaction,
                })
            count += 1
        self._timeline_url_var.set("")
        self._timeline_comment_var.set("")
        self._timeline_reaction_var.set("none")
        self._timeline_react_only_var.set(False)
        self._refresh()
        self._update_buttons()
        if react_only:
            self.set_status(f"Added react ({reaction}) for {count} profile(s): {url}")
        else:
            self.set_status(f"Added timeline share for {count} profile(s): {url}")

    def _build_comment_items(self, comment_raw, url, profiles):
        """Map 'profilename - comment' lines to their profiles.

        A single plain comment is applied to every profile. Multiple lines keep
        the profile-specific mapping behavior. If a line starts or ends with a
        matching profile name (split on ' - '), that profile gets the comment.
        Lines without a matching name fall back to the next unassigned profile.
        """
        lines = [l.strip() for l in comment_raw.splitlines() if l.strip()]
        if len(lines) == 1 and " - " not in lines[0]:
            return [{
                "action_type": "comment",
                "profile_name": profile,
                "post_url": url,
                "comment_text": lines[0],
            } for profile in profiles]

        name_lookup = {p.strip().lower(): p for p in profiles}
        unassigned = list(profiles)
        items = []
        for line in lines:
            profile = None
            comment_text = line
            if " - " in line:
                left, right = (part.strip() for part in line.split(" - ", 1))
                if left.lower() in name_lookup:
                    profile = name_lookup[left.lower()]
                    comment_text = right
                elif right.lower() in name_lookup:
                    profile = name_lookup[right.lower()]
                    comment_text = left
            if profile is None and unassigned:
                profile = unassigned.pop(0)
            if profile is None:
                continue
            if profile in unassigned:
                unassigned.remove(profile)
            items.append({
                "action_type": "comment",
                "profile_name": profile,
                "post_url": url,
                "comment_text": comment_text,
            })

        # Profiles left over when there are fewer comment lines than accounts
        # used to get nothing at all: 49 lines against 53 profiles queued 49
        # items and four accounts sat out the post without saying so. The
        # lines rotate instead, so every profile comments and no two adjacent
        # accounts share a line.
        if unassigned:
            texts = [i["comment_text"] for i in items] or lines
            for index, profile in enumerate(unassigned):
                items.append({
                    "action_type": "comment",
                    "profile_name": profile,
                    "post_url": url,
                    "comment_text": texts[index % len(texts)],
                })
        return items

    def _on_add_features(self):
        url = self._features_url_var.get().strip()
        if not url:
            return

        if not url.startswith("http"):
            messagebox.showerror("Invalid URL", "Post URL must start with http:// or https://")
            return

        profiles = cfg.list_profiles_for_browser()
        if not profiles:
            messagebox.showinfo("No Profiles", "No saved profiles found.")
            return

        comment = self._features_comment_text.get("1.0", tk.END).strip()
        if comment == COMMENT_PLACEHOLDER:
            comment = ""
        reaction = self._features_reaction_var.get().strip().lower()

        feature_names = []
        if self._feat_share_var.get():
            for profile_name in profiles:
                self._items.append({
                    "action_type": "share",
                    "profile_name": profile_name,
                    "post_url": url,
                })
            feature_names.append(f"Share ({len(profiles)})")

        if self._feat_story_var.get():
            for profile_name in profiles:
                self._items.append({
                    "action_type": "story",
                    "profile_name": profile_name,
                    "post_url": url,
                })
            feature_names.append(f"Story ({len(profiles)})")

        if self._feat_react_var.get():
            for profile_name in profiles:
                self._items.append({
                    "action_type": "react",
                    "profile_name": profile_name,
                    "post_url": url,
                    "reaction": reaction,
                })
            feature_names.append(f"React ({len(profiles)})")

        if self._feat_watch_var.get():
            raw_minutes = self._feat_watch_minutes_var.get().strip()
            try:
                minutes = float(raw_minutes) if raw_minutes else None
            except ValueError:
                messagebox.showerror("Watch minutes",
                                     "Minutes must be a number, or blank to watch "
                                     "until you press Stop.")
                return
            for profile_name in profiles:
                self._items.append({
                    "action_type": "watch",
                    "profile_name": profile_name,
                    "post_url": url,
                    "watch_minutes": minutes,
                })
            feature_names.append(f"Watch ({len(profiles)})")

        if self._feat_comment_var.get():
            comment_items = self._build_comment_items(comment, url, profiles)
            if not comment_items:
                messagebox.showwarning(
                    "No Profiles Matched",
                    "No comment line matched a profile name.\n"
                    "Use one line per profile, e.g.: profileName - comment")
                return
            self._items.extend(comment_items)
            feature_names.append(f"Comment ({len(comment_items)})")

        self._refresh()
        self._update_buttons()
        self.set_status(f"Added {', '.join(feature_names)}: {url}")

    def _update_onecomment_btn(self, *_):
        urls_raw = self._onecomment_urls_text.get("1.0", tk.END).strip()
        comment_raw = self._onecomment_comment_text.get("1.0", tk.END).strip()
        has_urls = bool(urls_raw) and urls_raw != ONECOMMENT_URLS_PLACEHOLDER
        has_comment = bool(comment_raw) and comment_raw != ONECOMMENT_COMMENT_PLACEHOLDER
        self._onecomment_btn.config(
            state="normal" if (has_urls and has_comment) else "disabled")

    def _on_add_one_comment_each(self):
        """Add comment items for every URL × every profile.

        URLs are one per line, comments one per line. On each URL the
        comment lines rotate across the profiles: the first account gets
        the first comment line, the second account the second, and so on
        (wrapping around if there are more accounts than comment lines).
        This way no two accounts post the same comment on the same post.
        """
        raw = self._onecomment_urls_text.get("1.0", tk.END).strip()
        if raw == ONECOMMENT_URLS_PLACEHOLDER:
            raw = ""
        if not raw:
            self.set_status("Enter at least one post URL")
            return

        urls = [line.strip() for line in raw.splitlines()
                if line.strip().startswith("http")]
        if not urls:
            messagebox.showerror(
                "Invalid URLs",
                "Enter one post URL per line, starting with http:// or https://")
            return

        comment = self._onecomment_comment_text.get("1.0", tk.END).strip()
        if comment == ONECOMMENT_COMMENT_PLACEHOLDER:
            comment = ""
        comment_lines = [line.strip() for line in comment.splitlines() if line.strip()]
        if not comment_lines:
            messagebox.showwarning("No Comment",
                                   "Enter the comment text (one comment per line).")
            return

        profiles = cfg.list_profiles_for_browser()
        if not profiles:
            messagebox.showinfo("No Profiles", "No saved profiles found.")
            return

        count = 0
        for url in urls:
            # Comment lines rotate across the profiles so each account
            # posts a different comment on this post.
            for j, profile_name in enumerate(profiles):
                self._items.append({
                    "action_type": "comment",
                    "profile_name": profile_name,
                    "post_url": url,
                    "comment_text": comment_lines[j % len(comment_lines)],
                })
                count += 1

        self._refresh()
        self._update_buttons()
        self.set_status(
            f"Added {count} comment item(s) — each account gets its own "
            f"comment on every URL")

    def _update_buttons(self):
        has_items = len(self._items) > 0
        has_sel = bool(self.queue_listbox.curselection())
        self.remove_btn.config(state="normal" if has_sel else "disabled")
        self.clear_btn.config(state="normal" if has_items else "disabled")
        self.run_btn.config(state="normal" if has_items else "disabled")

    def _on_select(self, event=None):
        self._update_buttons()

    def _on_load_presets(self):
        if not SAVED_FILE.exists():
            messagebox.showinfo("No Presets",
                                "No saved presets found.\n"
                                "Save URL + group pairs in the Share tab first.")
            return

        try:
            presets = json.loads(SAVED_FILE.read_text())
        except Exception:
            messagebox.showerror("Error", "Failed to load presets file.")
            return

        if not presets:
            messagebox.showinfo("No Presets", "No presets saved yet.")
            return

        self._items.clear()
        loaded = 0
        for p in presets:
            profile = p.get("profile")
            if not profile:
                continue
            if profile not in cfg.list_profiles():
                continue
            self._items.append({
                "action_type": "group",
                "profile_name": profile,
                "post_url": p["url"],
                "group_name": p["group"],
                "comment_text": p.get("comment", ""),
                "reaction": p.get("reaction", ""),
            })
            loaded += 1

        if not loaded:
            messagebox.showinfo("No Items",
                                "No presets with valid profiles found.\n"
                                "Save presets with a profile selected in the Share tab.")
            return

        self._refresh()
        self._update_buttons()
        self.set_status(f"Loaded {loaded} preset(s)")

    def _on_remove(self):
        sel = self.queue_listbox.curselection()
        if sel:
            idx = sel[0]
            del self._items[idx]
            self._refresh()
            self._update_buttons()

    def _on_clear(self):
        if not self._items:
            return
        if messagebox.askyesno("Clear Queue", "Remove all items from the queue?"):
            self.clear_all()

    def _on_run(self):
        if not self._items:
            return
        if not messagebox.askyesno("Start Queue",
                                    f"Process {len(self._items)} item(s) sequentially?"):
            return

        self.set_running(True)
        self.update_progress(0, len(self._items))
        self.set_status("Running...")
        if self._on_run_queue_cb:
            self._on_run_queue_cb(list(self._items))
