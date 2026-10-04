"""Bank a Facebook Lite session so a one-at-a-time device does not lose it.

One LDPlayer instance holds one live Facebook Lite session, and clones cannot
be driven on it (the display is bound to user 0 - see adb.clone_display_works).
So logging many accounts on one instance means logging one, then clearing the
app for the next - which throws the first session away.

This keeps it. Facebook Lite stores its session in a handful of data
subdirectories; the bulk of /data/data (app_modules, dex, lib-compressed) is
code the app regenerates on next launch, so only the session-bearing dirs are
saved. A banked session is a tarball named by the Facebook account id, plus a
note of which roster username it belongs to, under a local directory. It can
be restored into any instance later, which is also how these sessions would
be spread across several instances for concurrent use.

Nothing here decrypts or reads the session; it is moved as opaque bytes, the
same way the browser fleet moves its storage_state. It never leaves the
machine.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from src.mobile.adb import Device

# Everything under /data/data/<pkg> that carries session rather than code.
# Measured on Facebook Lite 529: ~11 MB, against ~150 MB for the whole tree.
SESSION_DIRS = (
    "databases", "shared_prefs", "files", "app_datastore",
    "app_light_prefs", "app_sslcache", "no_backup",
)

BANK_DIR = Path.home() / ".autoshare" / "fblite-sessions"


def _bank_dir() -> Path:
    BANK_DIR.mkdir(parents=True, exist_ok=True)
    return BANK_DIR


def export_session(dev: Device, username: str,
                   package: str = "com.facebook.lite") -> Path | None:
    """Save the current signed-in session. Returns the tarball path, or None.

    None when there is no session to save - checked against the app's own
    current_user_id, so an error screen that merely is not the login form is
    not banked as if it were an account.
    """
    fbid = dev.fblite_user_id(package)
    if not fbid:
        return None

    data = f"/data/data/{package}"
    present = [d for d in SESSION_DIRS
               if dev.su(f'[ -d {data}/{d} ] && echo yes').strip() == "yes"]
    if not present:
        return None

    on_device = f"/sdcard/_fbsess_{fbid}.tgz"
    dev.su(f"tar -czf {on_device} -C {data} {' '.join(present)}", timeout=180)

    out = _bank_dir() / f"{fbid}.tgz"
    _pull(dev, on_device, out)
    dev.shell(f"rm -f {on_device}")

    # The id is Facebook's; the username is how the operator knows the account.
    index = _bank_dir() / "index.json"
    rows = json.loads(index.read_text()) if index.exists() else {}
    rows[fbid] = {"username": username, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    index.write_text(json.dumps(rows, indent=2))
    return out


def restore_session(dev: Device, fbid: str,
                    package: str = "com.facebook.lite",
                    user: int | None = None) -> bool:
    """Put a banked session back. The app must already be installed.

    Restores into user 0 by default (`/data/data`); pass `user` for a clone's
    per-user path. The app must be stopped first, or it overwrites what is
    laid down on the way out.
    """
    tar = _bank_dir() / f"{fbid}.tgz"
    if not tar.exists():
        return False

    dev.stop(package, user=user)
    data = (f"/data/data/{package}" if user in (None, 0)
            else f"/data/user/{user}/{package}")
    on_device = f"/sdcard/_fbrestore_{fbid}.tgz"
    _push(dev, tar, on_device)

    # Owner of the data dir, to hand the unpacked files back to the app's uid.
    owner = dev.su(f"stat -c '%u:%g' {data}").strip() or "0:0"
    dev.su(f"tar -xzf {on_device} -C {data}")
    dev.su(f"chown -R {owner} {data}/" + "{databases,shared_prefs,files,"
           "app_datastore,app_light_prefs,app_sslcache,no_backup}")
    # SELinux context, or the app cannot read its own restored files.
    dev.su(f"restorecon -R {data} 2>/dev/null")
    dev.shell(f"rm -f {on_device}")
    return dev.fblite_user_id(package) == fbid if user in (None, 0) else True


def banked() -> dict:
    """{fbid: {username, saved_at}} for every session on this machine."""
    index = _bank_dir() / "index.json"
    return json.loads(index.read_text()) if index.exists() else {}


def _pull(dev: Device, remote: str, local: Path) -> None:
    subprocess.run([dev._adb, "-s", dev.serial, "pull", remote, str(local)],
                   capture_output=True, timeout=300,
                   env=_env(), check=True)


def _push(dev: Device, local: Path, remote: str) -> None:
    subprocess.run([dev._adb, "-s", dev.serial, "push", str(local), remote],
                   capture_output=True, timeout=300,
                   env=_env(), check=True)


def _env() -> dict:
    import os
    return {**os.environ, "MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*"}
