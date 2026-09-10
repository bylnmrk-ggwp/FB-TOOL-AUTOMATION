"""Central theme definitions for the FB TOOL AUTOMATION UI.

Supports light and dark mode. Raw-tk widgets (Canvas, Listbox, Text, Entry)
pull their colors from the active palette so the whole app can be re-themed
live via theme.set_mode() + each tab's apply_theme() method.

All colors are flat (solid). No gradients are used anywhere in the UI.
"""

# Fonts are resolved at runtime against the fonts actually installed on the
# system (resolve_fonts is called by MainWindow before building the UI), so
# the app never silently falls back to an ugly default font.
UI_FONT = "Poppins"
MONO_FONT = "Consolas"

_FONTS_RESOLVED = False


def resolve_fonts(root) -> tuple[str, str]:
    """Pick the best available UI and monospace fonts for the running system.

    Preference order for UI: Poppins → Segoe UI → Tk default.
    Preference order for mono: Consolas → Cascadia Mono → Courier New.

    Call once from the main window before building widgets. Returns
    (ui_font, mono_font) and caches the result.
    """
    global UI_FONT, MONO_FONT, _FONTS_RESOLVED
    if _FONTS_RESOLVED:
        return UI_FONT, MONO_FONT
    try:
        import tkinter.font as tkfont
        families = set(tkfont.families(root))
        for candidate in ("Poppins", "Segoe UI", "TkDefaultFont"):
            if candidate in families:
                UI_FONT = candidate
                break
        else:
            UI_FONT = "TkDefaultFont"
        for candidate in ("Consolas", "Cascadia Mono", "Courier New"):
            if candidate in families:
                MONO_FONT = candidate
                break
        else:
            MONO_FONT = "TkFixedFont"
    except Exception:
        pass
    _FONTS_RESOLVED = True
    return UI_FONT, MONO_FONT


THEMES = {
    # A minimalist palette: one neutral grey ramp, one accent, and semantic
    # colours only where they carry meaning. Every key the tabs already read
    # is kept, so apply_theme() implementations need no changes.
    "light": {
        # Surfaces: page, raised section, and the subtle fill used instead of
        # a border to separate a card from the page.
        "bg": "#fafafa",
        "card": "#ffffff",
        "surface": "#f4f4f5",
        "border": "#e7e7ea",
        "status_bg": "#f4f4f5",
        "canvas_bg": "#ffffff",

        # Text
        "fg": "#18181b",
        "heading": "#09090b",
        "muted": "#71717a",
        "status": "#52525b",
        "placeholder": "#a1a1aa",

        # The single accent. Nothing else in the UI is this colour.
        "accent": "#4f46e5",
        "accent_light": "#eef2ff",
        "accent_active": "#4338ca",
        "accent_hover": "#5b52ea",
        "accent_pressed": "#4338ca",
        "accent_disabled": "#c7d2fe",

        # Timeline share stays distinguishable from group share, but muted so
        # it does not compete with the accent for attention.
        "timeline": "#15803d",
        "timeline_active": "#166534",
        "timeline_hover": "#16a34a",
        "timeline_pressed": "#166534",
        "timeline_disabled": "#bbf7d0",

        # Semantic
        "success": "#15803d",
        "error": "#b91c1c",
        "warning": "#a16207",

        # The top bar now sits on the page, not on a dark slab.
        "toolbar_bg": "#fafafa",
        "toolbar_fg": "#18181b",
        "toolbar_accent": "#71717a",
        "header_hover": "#f4f4f5",
        "header_pressed": "#e7e7ea",

        # Inputs
        "input_bg": "#ffffff",
        "input_fg": "#18181b",

        # Ghost buttons: no resting fill or border, a tint on hover.
        "secondary": "#fafafa",
        "secondary_fg": "#3f3f46",
        "secondary_active": "#f4f4f5",
        "secondary_border": "#d4d4d8",
        "btn_hover": "#f0f0f1",
        "btn_pressed": "#e4e4e7",

        "disabled_bg": "#fafafa",
        "disabled_fg": "#a1a1aa",

        # Tabs read as text, so the inactive tab matches the page.
        "notebook_inactive": "#fafafa",
        "notebook_hover": "#f4f4f5",

        # Lists
        "list_bg": "#ffffff",
        "list_fg": "#18181b",
        "list_select_bg": "#eef2ff",
        "list_select_fg": "#312e81",
        "list_hover_bg": "#f4f4f5",
        "list_hover_fg": "#18181b",

        "track": "#e7e7ea",
        "dot_unknown": "#d4d4d8",
        "scroll_thumb": "#d4d4d8",
        "scroll_thumb_hover": "#a1a1aa",
    },
    "dark": {
        "bg": "#0f0f11",
        "card": "#17171a",
        "surface": "#1c1c20",
        "border": "#27272a",
        "status_bg": "#17171a",
        "canvas_bg": "#17171a",

        "fg": "#e4e4e7",
        "heading": "#fafafa",
        "muted": "#8b8b93",
        "status": "#a1a1aa",
        "placeholder": "#71717a",

        "accent": "#6d75f5",
        "accent_light": "#1e1b4b",
        "accent_active": "#818cf8",
        "accent_hover": "#7c83f7",
        "accent_pressed": "#5a62e0",
        "accent_disabled": "#2e2f5c",

        "timeline": "#2f9e5e",
        "timeline_active": "#3fb873",
        "timeline_hover": "#3fb873",
        "timeline_pressed": "#25804b",
        "timeline_disabled": "#1a3a28",

        "success": "#3fb873",
        "error": "#f0645a",
        "warning": "#d4a13a",

        "toolbar_bg": "#0f0f11",
        "toolbar_fg": "#e4e4e7",
        "toolbar_accent": "#8b8b93",
        "header_hover": "#1c1c20",
        "header_pressed": "#27272a",

        "input_bg": "#17171a",
        "input_fg": "#e4e4e7",

        "secondary": "#0f0f11",
        "secondary_fg": "#d4d4d8",
        "secondary_active": "#1c1c20",
        "secondary_border": "#3f3f46",
        "btn_hover": "#1f1f24",
        "btn_pressed": "#27272a",

        "disabled_bg": "#0f0f11",
        "disabled_fg": "#52525b",

        "notebook_inactive": "#0f0f11",
        "notebook_hover": "#1c1c20",

        "list_bg": "#17171a",
        "list_fg": "#e4e4e7",
        "list_select_bg": "#26264a",
        "list_select_fg": "#e4e4e7",
        "list_hover_bg": "#1f1f24",
        "list_hover_fg": "#e4e4e7",

        "track": "#27272a",
        "dot_unknown": "#3f3f46",
        "scroll_thumb": "#3f3f46",
        "scroll_thumb_hover": "#52525b",
    },
}


current = "light"


def get() -> dict:
    """Return the active theme palette dict."""
    return THEMES[current]


def set_mode(mode: str) -> str:
    """Set the active theme. Returns the mode actually set."""
    global current
    if mode in THEMES:
        current = mode
    return current


def toggle() -> str:
    """Switch between light and dark. Returns the new mode."""
    return set_mode("dark" if current == "light" else "light")
