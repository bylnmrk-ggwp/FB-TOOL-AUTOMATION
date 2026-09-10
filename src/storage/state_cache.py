"""Persistent per-profile cache of Playwright storage states.

Extracting a profile's login state means booting a full Brave instance
(~8-15s per profile, strictly sequential because Chromium's process
singleton locks the shared "User Data" dir). Facebook session cookies
stay valid for weeks, so caching the extracted state on disk lets warm
queue runs skip extraction entirely.

Validity is checked in two tiers:
  - offline (here): file age within TTL and the FB session cookies
    (c_user / xs) present and unexpired
  - live (existing code): every action already runs _is_logged_in();
    a needs_login result invalidates the cache entry so the next run
    re-extracts just that profile

Files live in ~/.autoshare/storage_states/, next to the app's other
per-user data.
"""

import json
import time
from pathlib import Path

from src.storage import config_manager as cfg

CACHE_DIR = Path.home() / ".autoshare" / "storage_states"

DEFAULT_TTL_DAYS = 3


def _path(profile_name: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in " -_()." else "_"
                   for ch in profile_name).strip()
    return CACHE_DIR / f"{safe or 'profile'}.json"


def save_state(profile_name: str, state: dict):
    """Persist a freshly extracted storage state. Best-effort."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _path(profile_name).write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def load_state(profile_name: str) -> dict | None:
    """Return the cached storage state, or None if absent/stale/invalid."""
    try:
        path = _path(profile_name)
        if not path.exists():
            return None
        ttl_days = cfg.get_setting("state_cache_ttl_days", DEFAULT_TTL_DAYS)
        if time.time() - path.stat().st_mtime > float(ttl_days) * 86400:
            return None
        state = json.loads(path.read_text(encoding="utf-8"))
        # Offline validity: FB session cookies must exist and be unexpired
        now = time.time()
        cookies = {c.get("name"): c for c in state.get("cookies", [])}
        for name in ("c_user", "xs"):
            c = cookies.get(name)
            if not c:
                return None
            expires = c.get("expires", -1)
            if expires not in (-1, None) and expires < now:
                return None
        return state
    except Exception:
        return None


def invalidate(profile_name: str):
    """Drop a profile's cached state (e.g. it turned out logged-out)."""
    try:
        path = _path(profile_name)
        if path.exists():
            path.unlink()
    except Exception:
        pass


def clear_all():
    """Remove every cached state."""
    try:
        if CACHE_DIR.exists():
            for f in CACHE_DIR.glob("*.json"):
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass
