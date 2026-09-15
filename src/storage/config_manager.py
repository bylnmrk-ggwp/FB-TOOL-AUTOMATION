import json
import os
import time
from pathlib import Path

AUTOSHARE_DIR = Path.home() / ".autoshare"
CREDENTIALS_FILE = AUTOSHARE_DIR / "credentials.json"
BRAVE_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "User Data"
CONFIG_FILE = AUTOSHARE_DIR / "config.json"

_config_cache: dict | None = None
_config_cache_time: float = 0
_CONFIG_TTL = 2.0  # seconds


def _ensure_dir():
    AUTOSHARE_DIR.mkdir(parents=True, exist_ok=True)


def _load_config() -> dict:
    """Load the full config.json contents with a short-lived cache."""
    global _config_cache, _config_cache_time
    now = time.monotonic()
    if _config_cache is not None and (now - _config_cache_time) < _CONFIG_TTL:
        return _config_cache
    if CONFIG_FILE.exists():
        try:
            _config_cache = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            _config_cache_time = now
            return _config_cache
        except Exception:
            pass
    _config_cache = {}
    _config_cache_time = now
    return _config_cache


def _save_config(config: dict):
    global _config_cache, _config_cache_time
    _ensure_dir()
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    _config_cache = config
    _config_cache_time = time.monotonic()


def list_profiles() -> list[str]:
    """List all saved Brave profile names, sorted by Brave profile number (ascending).
    
    Extracts the number from the profile path (e.g. 'Profile 1' -> 1, 'Default' -> 0)
    and sorts profiles by that number so they appear in order.
    """
    import re
    config = _load_config()
    profiles = config.get("profiles", {})
    
    def _sort_key(name: str) -> int:
        path = profiles[name] if isinstance(profiles[name], str) else ""
        # Extract number from path like "Profile 1", "Profile 2", or "Default" -> 0
        match = re.search(r'Profile\s+(\d+)', path, re.IGNORECASE)
        if match:
            return int(match.group(1))
        if 'Default' in path:
            return 0
        return 9999  # Unknown profiles go to the end
    
    return sorted(profiles.keys(), key=_sort_key)


def get_profile_path(name: str) -> str | None:
    """Get the original Brave profile directory path for a saved profile name.
    
    Returns the full path like: C:/Users/.../Brave-Browser/User Data/Default
    or None if the profile doesn't exist.
    """
    config = _load_config()
    return config.get("profiles", {}).get(name)


def save_profile(name: str, brave_full_path: str):
    """Save a Brave profile path reference under the given name.
    
    No files are copied — only the path reference is stored. Playwright
    will use the original Brave profile directory directly, preserving
    all existing cookies and sessions.
    """
    config = _load_config()
    config.setdefault("profiles", {})
    config["profiles"][name] = brave_full_path
    _save_config(config)


def delete_profile(name: str) -> bool:
    """Remove a saved profile reference from config.

    The original Brave profile is never touched.
    """
    config = _load_config()
    if name in config.get("profiles", {}):
        del config["profiles"][name]
        _save_config(config)
        return True
    return False


# ── Credential persistence ────────────────────────────────


def clear_credentials():
    """Remove saved credentials file."""
    try:
        if CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
    except Exception:
        pass


# ── Brave profile detection ──────────────────────────────


def list_brave_profiles() -> list[dict]:
    """List available Brave profiles with their names and directory names.
    
    Returns something like:
    [
        {"dir_name": "Default", "name": "Default", "display": "Person 1", "email": ""},
        {"dir_name": "Profile 1", "name": "Work", "display": "user@work.com", "email": "user@work.com"},
    ]
    """
    profiles = []
    local_state_path = BRAVE_USER_DATA / "Local State"
    if not local_state_path.exists():
        return profiles
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        info_cache = state.get("profile", {}).get("info_cache", {})
        for dir_name, info in info_cache.items():
            if dir_name.startswith(".") or dir_name in ("Guest Profile", "System Profile"):
                continue
            name = info.get("name", dir_name)
            user_name = info.get("user_name", "")
            gaia_name = info.get("gaia_name", "")
            # Use gaia_name or user_name if available; otherwise fall back
            # to the dir_name (e.g. "Profile 1") instead of the numeric
            # Brave name which is meaningless.
            display = gaia_name or user_name or dir_name
            profiles.append({
                "dir_name": dir_name,
                "name": name,
                "display": display,
                "email": user_name,
                "full_path": str(BRAVE_USER_DATA / dir_name),
            })
    except Exception:
        pass
    return profiles


# ── General settings ──────────────────────────────────────


def get_setting(key: str, default=None):
    """Get a generic setting from config, returning default if not found."""
    config = _load_config()
    return config.get("settings", {}).get(key, default)


def save_setting(key: str, value):
    """Save a generic setting to config."""
    config = _load_config()
    config.setdefault("settings", {})
    config["settings"][key] = value
    _save_config(config)


def auto_sync_brave_profiles() -> list[str]:
    """Fully sync saved profiles with what Brave actually has.

    Adds missing profiles, removes deleted ones, renames old entries
    to match Brave profile names, and updates paths.
    Returns list of newly added profile names.
    """
    brave_profiles = list_brave_profiles()
    brave_path_to_bp = {bp["full_path"]: bp for bp in brave_profiles}
    brave_paths = set(brave_path_to_bp.keys())

    config = _load_config()
    old_profiles = config.get("profiles", {})
    new_profiles: dict[str, str] = {}
    added: list[str] = []

    # 1. Rename/update existing profiles to match Brave's current names
    for old_name, old_path in old_profiles.items():
        bp = brave_path_to_bp.get(old_path)
        if bp is None:
            # Path no longer exists in Brave — skip (will be removed)
            continue

        brave_name = bp["name"] or bp["dir_name"]
        
        # Extract Brave short name (e.g., "Profile 1" -> "1", "Default" -> "Default")
        import re
        match = re.search(r'Profile\s+(\d+)', brave_name, re.IGNORECASE)
        if match:
            brave_short = match.group(1)
        elif brave_name.lower() == "default":
            brave_short = "Default"
        else:
            brave_short = brave_name
        
        # Preserve the Facebook name if it exists in format "1 - Facebook Name"
        # Check if old_name follows the pattern "{brave_short} - {facebook_name}"
        if " - " in old_name:
            parts = old_name.split(" - ", 1)
            if parts[0] == brave_short:
                # Already in correct format, keep it
                correct_name = old_name
            else:
                # Update the Brave part but keep the Facebook name
                correct_name = f"{brave_short} - {parts[1]}"
        elif old_name.startswith(f"{brave_short} "):
            # Has brave_short prefix, keep it
            correct_name = old_name
        else:
            # No Facebook name detected, use Brave name
            correct_name = brave_short
        
        if correct_name not in new_profiles:
            new_profiles[correct_name] = old_path
        else:
            # Name collision — keep with counter
            counter = 2
            while f"{correct_name} ({counter})" in new_profiles:
                counter += 1
            new_profiles[f"{correct_name} ({counter})"] = old_path

        # Update facebook_urls key if renamed
        if old_name != correct_name and "facebook_urls" in config:
            fb_urls = config.get("facebook_urls", {})
            if old_name in fb_urls and correct_name not in fb_urls:
                fb_urls[correct_name] = fb_urls.pop(old_name)
                config["facebook_urls"] = fb_urls

    # 2. Add every Brave profile that isn't saved yet
    existing_paths = set(new_profiles.values())

    for bp in brave_profiles:
        full_path = bp["full_path"]
        if full_path in existing_paths:
            continue

        brave_name = bp["name"] or bp["dir_name"]
        
        # Extract short name for consistency
        import re
        match = re.search(r'Profile\s+(\d+)', brave_name, re.IGNORECASE)
        if match:
            name = match.group(1)
        elif brave_name.lower() == "default":
            name = "Default"
        else:
            name = brave_name

        if name in new_profiles:
            counter = 2
            while f"{name} ({counter})" in new_profiles:
                counter += 1
            name = f"{name} ({counter})"

        new_profiles[name] = full_path
        added.append(name)

    # Entries for the other browser live in the same map and are none of this
    # sync's business: dropping them would unlink every Chromium account.
    for name, path in old_profiles.items():
        if _under(path, BRAVE_USER_DATA) or path in new_profiles.values():
            continue
        new_profiles.setdefault(name, path)

    config["profiles"] = new_profiles
    _save_config(config)

    return added


# ── Profiles of whichever browser is selected ─────────────────


def _under(path: str, root) -> bool:
    """Whether a saved path sits inside one browser's profile root."""
    try:
        return str(Path(path).resolve()).lower().startswith(str(Path(root).resolve()).lower())
    except Exception:
        return False


def list_chromium_profiles() -> list[dict]:
    """Every Chromium profile directory this PC has, in the shape
    list_brave_profiles() returns.

    A Chromium profile is a directory and nothing else - there is no Local
    State info_cache to read, and the directory name is the account it was
    created for.
    """
    from src.core import browser_choice
    root = browser_choice.CHROMIUM_USER_DATA
    profiles = []
    try:
        entries = sorted(d for d in root.iterdir() if d.is_dir())
    except Exception:
        return profiles
    for d in entries:
        profiles.append({
            "dir_name": d.name,
            "name": d.name,
            "display": d.name,
            "email": d.name if "@" in d.name else "",
            "full_path": str(d),
        })
    return profiles


def list_browser_profiles() -> list[dict]:
    """The profiles of the browser the automation is set to drive."""
    from src.core import browser_choice
    return (list_chromium_profiles()
            if browser_choice.current_browser() == browser_choice.CHROMIUM
            else list_brave_profiles())


def auto_sync_chromium_profiles() -> list[str]:
    """Save an entry for every Chromium profile directory, and drop entries
    whose directory is gone. Brave entries are left alone.

    The directory name IS the profile name here, so there is none of Brave's
    renaming: one account, one directory, one entry.
    """
    from src.core import browser_choice
    root = browser_choice.CHROMIUM_USER_DATA
    config = _load_config()
    saved = dict(config.get("profiles", {}))
    on_disk = {p["full_path"]: p["dir_name"] for p in list_chromium_profiles()}

    kept = {name: path for name, path in saved.items()
            if not _under(path, root) or path in on_disk}
    known = set(kept.values())
    added = []
    for path, dir_name in on_disk.items():
        if path in known:
            continue
        name = dir_name
        counter = 2
        while name in kept:
            name = f"{dir_name} ({counter})"
            counter += 1
        kept[name] = path
        added.append(name)

    if kept != saved:
        config["profiles"] = kept
        _save_config(config)
    return added


def list_profiles_for_browser() -> list[str]:
    """Saved profile names this machine drives, for the selected browser.

    Two filters, both about what this PC can actually open. The saved map
    holds profiles of both browsers - a Brave profile lives under Brave's
    User Data, a Chromium one under CHROMIUM_USER_DATA - and neither browser
    can open the other's. And where a fleet is split across several PCs, this
    machine owns its share of it; on a single-PC setup that share is all of
    them, which is the default.
    """
    from src.core import browser_choice
    root = browser_choice.user_data_root()
    config = _load_config()
    names = [name for name, path in config.get("profiles", {}).items()
             if _under(path, root)]
    try:
        from src.core import fleet
        return fleet.mine(names)
    except Exception:
        return names        # a broken share must not hide the whole fleet


def auto_sync_profiles() -> list[str]:
    """Sync saved profiles with whichever browser is selected."""
    from src.core import browser_choice
    return (auto_sync_chromium_profiles()
            if browser_choice.current_browser() == browser_choice.CHROMIUM
            else auto_sync_brave_profiles())


# ── Facebook Profile URLs ─────────────────────────────────


def save_facebook_url(profile_name: str, facebook_url: str):
    """Save the Facebook profile URL for a given Brave profile.
    
    Args:
        profile_name: The Brave profile name (e.g., "Default", "Profile 1")
        facebook_url: The Facebook profile URL (e.g., "https://www.facebook.com/username")
    """
    config = _load_config()
    config.setdefault("facebook_urls", {})
    config["facebook_urls"][profile_name] = facebook_url
    _save_config(config)


# ── Share Delay Settings ──────────────────────────────────


def get_share_delays() -> dict:
    """Get delay settings for sharing to avoid spam detection.
    
    Returns dict with:
        - between_shares_min: Minimum seconds between group shares (default: 15)
        - between_shares_max: Maximum seconds between group shares (default: 45)
        - after_share_button_min: Min seconds after clicking Share button (default: 2)
        - after_share_button_max: Max seconds after clicking Share button (default: 5)
        - after_post_min: Min seconds to wait after posting (default: 8)
        - after_post_max: Max seconds to wait after posting (default: 15)
        - between_joins_min: Min seconds between group joins (default: 3)
        - between_joins_max: Max seconds between group joins (default: 5)
        - join_retry_min: Min back-off after one join timeout (default: 8)
        - join_retry_max: Max back-off after one join timeout (default: 12)
        - join_backoff_min: Min back-off after 3 join timeouts (default: 20)
        - join_backoff_max: Max back-off after 3 join timeouts (default: 30)
    """
    config = _load_config()
    defaults = {
        "between_shares_min": 15,
        "between_shares_max": 45,
        "after_share_button_min": 2,
        "after_share_button_max": 5,
        "after_post_min": 8,
        "after_post_max": 15,
        "between_joins_min": 3,
        "between_joins_max": 5,
        "join_retry_min": 8,
        "join_retry_max": 12,
        "join_backoff_min": 20,
        "join_backoff_max": 30,
    }
    delays = config.get("share_delays", {})
    return {**defaults, **delays}


def save_share_delays(delays: dict):
    """Save delay settings for sharing.
    
    Args:
        delays: Dict with delay settings (see get_share_delays for keys)
    """
    config = _load_config()
    config["share_delays"] = delays
    _save_config(config)


# ── Comment Delay Settings ────────────────────────────────


def get_comment_delays() -> dict:
    """Get delay settings for commenting to avoid spam detection.
    
    Returns dict with:
        - between_comments_min: Minimum seconds between comment attempts (default: 10)
        - between_comments_max: Maximum seconds between comment attempts (default: 30)
        - after_navigation_min: Min seconds after navigating to post (default: 2)
        - after_navigation_max: Max seconds after navigating to post (default: 4)
        - after_clicking_box_min: Min seconds after clicking comment box (default: 1)
        - after_clicking_box_max: Max seconds after clicking comment box (default: 2)
        - after_posting_min: Min seconds after posting comment (default: 3)
        - after_posting_max: Max seconds after posting comment (default: 5)
    """
    config = _load_config()
    defaults = {
        "between_comments_min": 10,
        "between_comments_max": 30,
        "after_navigation_min": 2,
        "after_navigation_max": 4,
        "after_clicking_box_min": 1,
        "after_clicking_box_max": 2,
        "after_posting_min": 3,
        "after_posting_max": 5,
    }
    delays = config.get("comment_delays", {})
    return {**defaults, **delays}


def save_comment_delays(delays: dict):
    """Save delay settings for commenting.
    
    Args:
        delays: Dict with delay settings (see get_comment_delays for keys)
    """
    config = _load_config()
    config["comment_delays"] = delays
    _save_config(config)

