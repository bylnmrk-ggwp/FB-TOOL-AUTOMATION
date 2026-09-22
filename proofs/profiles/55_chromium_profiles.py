"""Chromium profiles: one self-contained directory per account, created on
demand, and openable side by side.

Brave keeps every profile inside one shared "User Data" tree and selects one
with --profile-directory, which is why only one can be driven at a time.
Chromium here gets a directory per account and no --profile-directory at all,
so five logins can run at once without sharing a lock or a cookie key.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("chromium profiles")  # noqa: F821

from src.core import browser_choice as bc  # noqa: E402
from src.core import chromium_profiles as cp  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402

_saved = cfg.get_setting(bc.SETTING_KEY, None)
_made = []
try:
    cfg.save_setting(bc.SETTING_KEY, "chromium")

    # A profile is a directory of its own, inside our root, named for the account.
    path = cp.ensure_profile("verify_cp@example.com")
    _made.append(path)
    if not path.is_dir():
        failures.append(f"chromium profiles: ensure_profile did not create {path}")  # noqa: F821
    if bc.CHROMIUM_USER_DATA not in path.parents:
        failures.append(f"chromium profiles: {path} is outside the profile root")  # noqa: F821

    # Twice is idempotent - the second call must not wipe a logged-in profile.
    marker = path / "marker.txt"
    marker.write_text("session", encoding="utf-8")
    again = cp.ensure_profile("verify_cp@example.com")
    if again != path or not marker.exists():
        failures.append("chromium profiles: ensure_profile is not idempotent - "  # noqa: F821
                        "a second call must keep existing profile data")

    # Two accounts never share a directory, or they share a Facebook session.
    other = cp.ensure_profile("verify_cp2@example.com")
    _made.append(other)
    if other == path:
        failures.append("chromium profiles: two accounts resolved to one directory")  # noqa: F821
finally:
    for p in _made:
        try:
            import shutil
            shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
    if _saved is None:
        conf = cfg._load_config()
        conf.pop(bc.SETTING_KEY, None)
        cfg._save_config(conf)
    else:
        cfg.save_setting(bc.SETTING_KEY, _saved)

# Opening a profile must not use Brave's layout when the browser is Chromium:
# the directory IS the user-data-dir, and --profile-directory must be absent.
import inspect  # noqa: E402
from src.core.facebook_automation import FacebookAutomation  # noqa: E402
src = inspect.getsource(FacebookAutomation.start_browser)
if "profile_directory" not in src.replace("-", "_"):
    failures.append("chromium profiles: start_browser no longer sets a profile "  # noqa: F821
                    "directory at all - Brave still needs one")
if "browser_choice" not in src:
    failures.append("chromium profiles: start_browser still assumes Brave's layout "  # noqa: F821
                    "for every browser")

print("FAILED" if [f for f in failures if "chromium profiles" in f] else "ok")  # noqa: F821
