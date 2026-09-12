"""Proof: both palettes carry the sidebar/brand keys and MOTION durations
exist. Run by verify.py with globals failures, step and ROOT."""
import sys
sys.path.insert(0, str(ROOT))

step("theme keys")
from src.ui import theme as _theme
_NEW_KEYS = ("sidebar_bg", "sidebar_fg", "sidebar_muted", "sidebar_active_bg",
             "sidebar_active_fg", "sidebar_hover_bg", "sidebar_border", "brand",
             "header_bg", "chip_bg", "chip_fg")
for _mode in ("light", "dark"):
    for _k in _NEW_KEYS:
        if _k not in _theme.THEMES[_mode]:
            failures.append(f"theme.THEMES[{_mode!r}] missing {_k!r}")
if set(_theme.THEMES["light"]) != set(_theme.THEMES["dark"]):
    failures.append("light/dark palettes have different key sets")
for _k in ("page", "sidebar", "press", "theme", "count", "progress"):
    if not isinstance(getattr(_theme, "MOTION", {}).get(_k), int):
        failures.append(f"theme.MOTION[{_k!r}] missing")
print("ok" if not [f for f in failures if "theme" in f] else "FAILED")
