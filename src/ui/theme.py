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
    "light": {
        "bg": "#f3f4f6",
        "fg": "#111827",
        "card": "#ffffff",
        "heading": "#0f172a",
        "accent": "#4f46e5",
        "accent_light": "#e0e7ff",
        "accent_active": "#4338ca",
        "accent_disabled": "#a5b4fc",
        "timeline": "#059669",
        "timeline_active": "#047857",
        "timeline_disabled": "#a7f3d0",
        "toolbar_bg": "#0f172a",
        "toolbar_fg": "#f8fafc",
        "toolbar_accent": "#a5b4fc",
        "status_bg": "#e5e7eb",
        "border": "#e5e7eb",
        "input_bg": "#ffffff",
        "input_fg": "#111827",
        "muted": "#6b7280",
        "status": "#4b5563",
        "success": "#059669",
        "error": "#dc2626",
        "warning": "#d97706",
        "secondary": "#ffffff",
        "secondary_fg": "#1f2937",
        "secondary_active": "#eef2ff",
        "secondary_border": "#c7d2fe",
        "btn_hover": "#f3f4f6",
        "btn_pressed": "#e5e7eb",
        "accent_hover": "#6366f1",
        "accent_pressed": "#4338ca",
        "timeline_hover": "#10b981",
        "timeline_pressed": "#047857",
        "header_hover": "#1e293b",
        "header_pressed": "#0b1220",
        "notebook_inactive": "#e5e7eb",
        "notebook_hover": "#f9fafb",
        "disabled_bg": "#f1f5f9",
        "disabled_fg": "#9ca3af",
        "list_bg": "#ffffff",
        "list_fg": "#111827",
        "list_select_bg": "#4f46e5",
        "list_select_fg": "#ffffff",
        "canvas_bg": "#ffffff",
        "track": "#e5e7eb",
        "placeholder": "#9ca3af",
        "dot_unknown": "#cbd5e1",
        "list_hover_bg": "#eef2ff",
        "list_hover_fg": "#1f2937",
    },
    "dark": {
        "bg": "#0b0f19",
        "fg": "#e2e8f0",
        "card": "#111827",
        "heading": "#f8fafc",
        "accent": "#6366f1",
        "accent_light": "#312e81",
        "accent_active": "#818cf8",
        "accent_disabled": "#312e5f",
        "timeline": "#10b981",
        "timeline_active": "#34d399",
        "timeline_disabled": "#064e3b",
        "toolbar_bg": "#070b14",
        "toolbar_fg": "#f1f5f9",
        "toolbar_accent": "#818cf8",
        "status_bg": "#0f172a",
        "border": "#1e293b",
        "input_bg": "#0f172a",
        "input_fg": "#f1f5f9",
        "muted": "#64748b",
        "status": "#94a3b8",
        "success": "#34d399",
        "error": "#f87171",
        "warning": "#fbbf24",
        "secondary": "#1e293b",
        "secondary_fg": "#e2e8f0",
        "secondary_active": "#334155",
        "secondary_border": "#475569",
        "btn_hover": "#263344",
        "btn_pressed": "#1b2434",
        "accent_hover": "#818cf8",
        "accent_pressed": "#4f46e5",
        "timeline_hover": "#34d399",
        "timeline_pressed": "#059669",
        "header_hover": "#16202f",
        "header_pressed": "#0b0f1a",
        "notebook_inactive": "#1e293b",
        "notebook_hover": "#16202f",
        "disabled_bg": "#111827",
        "disabled_fg": "#475569",
        "list_bg": "#0f172a",
        "list_fg": "#e2e8f0",
        "list_select_bg": "#6366f1",
        "list_select_fg": "#ffffff",
        "canvas_bg": "#111827",
        "track": "#1e293b",
        "placeholder": "#64748b",
        "dot_unknown": "#475569",
        "list_hover_bg": "#1e2a44",
        "list_hover_fg": "#e2e8f0",
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
