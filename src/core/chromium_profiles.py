"""Chromium profiles: one directory per account, created on demand.

Brave keeps every profile inside one shared "User Data" tree, selected with
--profile-directory, and binds the cookie key to that tree. Both facts force
logins to run one at a time. A Chromium profile is just a user-data
directory, so each account gets its own and several can be driven at once.

Creating one needs no registry edit and no Local State surgery - unlike
scripts/provision_profiles.py, which has to register Brave profiles or Brave
drops them. Chromium fills a fresh directory itself on first launch.
"""
from pathlib import Path

from src.core import browser_choice
from src.storage import config_manager as cfg
from src.storage import database as db


def ensure_profile(profile_name: str) -> Path:
    """The directory for this account, created if missing.

    Idempotent on purpose: a second call on a profile that has already logged
    in must leave its cookies alone, so this only ever creates the directory.
    """
    path = browser_choice.profile_dir(profile_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def provision_all(log=print) -> dict:
    """Give every roster account a Chromium profile and link it.

    Returns {"created", "already", "skipped"} counts. Accounts Facebook has
    disabled are left alone: a profile for them would never be driven.
    """
    created = already = skipped = 0
    registered = set(cfg.list_profiles())
    for acct in db.list_accounts():
        username = (acct.get("username") or "").strip()
        if not username:
            skipped += 1
            continue
        if (acct.get("status") or "") == "disabled":
            skipped += 1
            continue
        path = browser_choice.profile_dir(username)
        existed = path.exists()
        ensure_profile(username)
        # The profile is named for the account: with a directory each there is
        # no "Profile 7" numbering to keep in step with anything.
        if username not in registered or cfg.get_profile_path(username) != str(path):
            cfg.save_profile(username, str(path))
        if (acct.get("linked_profile") or "") != username:
            db.link_account(username, username)
        if existed:
            already += 1
        else:
            created += 1
    log(f"Chromium profiles: {created} created, {already} already there, "
        f"{skipped} skipped (disabled or nameless)")
    return {"created": created, "already": already, "skipped": skipped}
