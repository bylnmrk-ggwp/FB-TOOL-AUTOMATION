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
