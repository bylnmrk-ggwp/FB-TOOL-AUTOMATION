"""The browser the automation drives - Brave - and where its profiles live.

There used to be a second choice here. Playwright's own Chromium was added
because Brave 152 binds cookie encryption to the user-data-dir
(`os_crypt.app_bound_encrypted_key` in Local State), so a profile copied to
another directory comes up with cookies the destination cannot decrypt; that
one fact forces logins to run inside the real Brave directory, one at a time.
A Chromium profile is self-contained, so one directory per account could log
in side by side.

That path is gone: every session the fleet actually banks lives in Brave's
own User Data, and carrying a second browser meant two profile layouts, two
user-data roots that must never mix, and a branch in every launch site. What
remains is the Brave behaviour, stated once.
"""
import os
from pathlib import Path

BRAVE = "brave"

BRAVE_EXE = Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
BRAVE_USER_DATA = (Path(os.environ.get("LOCALAPPDATA", ""))
                   / "BraveSoftware" / "Brave-Browser" / "User Data")


def current_browser() -> str:
    """The browser being driven. Always Brave."""
    return BRAVE


def executable_path() -> str:
    """What to hand Playwright as executable_path."""
    return str(BRAVE_EXE)


def user_data_root() -> Path:
    """The directory that holds Brave's profiles."""
    return BRAVE_USER_DATA


def supports_parallel_login() -> bool:
    """Whether several profiles can be driven at once. Brave cannot.

    Chromium's ProcessSingleton locks the shared User Data directory, and the
    cookie key is bound to that directory anyway, so a login wave runs one
    profile at a time.
    """
    return False


# ── Window layout ─────────────────────────────────────

# Whether a login wave shows its windows. Off means headless, which is
# faster and what an unattended run wants; on tiles them so the operator can
# watch the whole wave at once instead of one on top of another.
GRID_KEY = "login_window_grid"


def show_login_windows() -> bool:
    from src.storage import config_manager as cfg
    return str(cfg.get_setting(GRID_KEY, "0")).strip().lower() in ("1", "true", "yes", "on")


# Chromium's own coordinate unit while tiling, as a fraction of a screen
# pixel. It has a minimum window width of about 515 units, which is wider
# than a 5x5 cell on any normal screen; at 0.5 a unit is half a pixel, the
# space is twice as wide in units, and the cell clears the minimum.
GRID_SCALE = 0.5


def grid_slot(index: int, count: int, screen_w: int = 1536,
              screen_h: int = 864) -> tuple[int, int, int, int]:
    """(x, y, width, height) for one window of a wave of `count`.

    screen_w/screen_h are in the browser's own units - what the page reports
    as screen.availWidth - not screen pixels.

    The squarest grid that holds them all: a wave of 25 becomes 5x5, five
    becomes 3x2 rather than a row of slivers. Index wraps, so a caller that
    miscounts still gets a real rectangle instead of an exception mid-run.
    """
    import math
    count = max(1, int(count))
    index = int(index) % count
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    w = max(1, screen_w // cols)
    h = max(1, screen_h // rows)
    return ((index % cols) * w, (index // cols) * h, w, h)
