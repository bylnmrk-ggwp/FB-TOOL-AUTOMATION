"""Which browser the automation drives, and where its profiles live.

Every launch used to point at one absolute Brave path. That mattered more
than it looked: Brave 152 binds cookie encryption to the user-data-dir
(`os_crypt.app_bound_encrypted_key` in Local State), so a profile copied to
another directory comes up with cookies the destination cannot decrypt. That
single fact forces logins to run one at a time inside the real Brave
directory and makes `scripts/login_parallel.py` produce sessions that look
signed in and are not.

Playwright's own Chromium has no such binding, so profiles can live one per
directory and log in side by side. Both browsers are supported, chosen by the
`browser` setting, and they never share a user-data root: neither can read
the other's cookie store, so mixing them would quietly destroy sessions.
"""
import os
from pathlib import Path

SETTING_KEY = "browser"
BRAVE = "brave"
CHROMIUM = "chromium"
KNOWN = (BRAVE, CHROMIUM)
DEFAULT = BRAVE

BRAVE_EXE = Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
BRAVE_USER_DATA = (Path(os.environ.get("LOCALAPPDATA", ""))
                   / "BraveSoftware" / "Brave-Browser" / "User Data")
# One directory per account, under our own tree: Chromium keeps each profile
# self-contained, which is what allows several to run at once.
CHROMIUM_USER_DATA = Path.home() / ".autoshare" / "chromium-profiles"


def current_browser() -> str:
    """The configured browser, always one of KNOWN."""
    from src.storage import config_manager as cfg
    choice = str(cfg.get_setting(SETTING_KEY, DEFAULT) or DEFAULT).strip().lower()
    return choice if choice in KNOWN else DEFAULT


def executable_path() -> str | None:
    """What to hand Playwright as executable_path.

    None for Chromium: Playwright then launches the build it installed and
    version-matched to itself, which is one less thing to keep in step.
    """
    return None if current_browser() == CHROMIUM else str(BRAVE_EXE)


def user_data_root() -> Path:
    """The directory that holds this browser's profiles."""
    return CHROMIUM_USER_DATA if current_browser() == CHROMIUM else BRAVE_USER_DATA


def supports_parallel_login() -> bool:
    """Whether several profiles can be driven at once.

    Brave cannot: Chromium's ProcessSingleton locks the shared User Data
    directory, and its cookie key is bound to that directory anyway. With a
    directory per account, nothing is shared and nothing is locked.
    """
    return current_browser() == CHROMIUM


def profile_dir(profile_name: str) -> Path:
    """Where one account's Chromium profile lives. Brave profiles keep their
    own layout (a `Profile N` folder inside the shared User Data), so this is
    only meaningful for Chromium."""
    safe = "".join(ch if (ch.isalnum() or ch in "-_.@") else "_"
                   for ch in (profile_name or "")).strip("_") or "profile"
    return CHROMIUM_USER_DATA / safe


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
