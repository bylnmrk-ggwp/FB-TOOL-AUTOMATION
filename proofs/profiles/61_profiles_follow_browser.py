"""Adding and scanning profiles follow the selected browser.

The Profiles tab was written when Brave was the only browser: Add opened
Brave's profile picker and Scan read Brave's Local State, so with Chromium
selected both offered profiles no run would ever open. Worse, the Brave sync
rewrote the whole saved-profile map from what Brave had, which would unlink
every Chromium account in it.
"""
import inspect
import shutil
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("profiles follow browser")  # noqa: F821

from src.core import browser_choice as bc  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402
from src.ui.profiles_tab import ProfilesTab  # noqa: E402

_saved_browser = cfg.get_setting(bc.SETTING_KEY, None)
_saved_profiles = dict(cfg._load_config().get("profiles", {}))
_made = []
try:
    cfg.save_setting(bc.SETTING_KEY, "chromium")

    # A Chromium profile directory shows up as a profile of this browser.
    path = bc.profile_dir("verify_scan@example.com")
    path.mkdir(parents=True, exist_ok=True)
    _made.append(path)
    found = [p for p in cfg.list_browser_profiles() if p["full_path"] == str(path)]
    if not found:
        failures.append("profiles follow browser: a Chromium profile directory is not "  # noqa: F821
                        "listed as a profile")

    # Scanning saves it without being told where Brave keeps anything.
    conf = cfg._load_config()
    conf["profiles"] = {"KeepBrave": str(bc.BRAVE_USER_DATA / "Profile 9")}
    cfg._save_config(conf)
    cfg.auto_sync_profiles()
    saved = cfg._load_config().get("profiles", {})
    if str(path) not in saved.values():
        failures.append("profiles follow browser: scanning did not pick up the "  # noqa: F821
                        "Chromium profile")
    if "KeepBrave" not in saved:
        failures.append("profiles follow browser: the Chromium scan deleted a Brave "  # noqa: F821
                        "profile entry")

    # A directory that is gone stops being a saved profile.
    shutil.rmtree(path, ignore_errors=True)
    cfg.auto_sync_profiles()
    if str(path) in cfg._load_config().get("profiles", {}).values():
        failures.append("profiles follow browser: a deleted Chromium directory is "  # noqa: F821
                        "still saved as a profile")

    # The Brave sync must leave Chromium entries alone for the same reason.
    keep = bc.CHROMIUM_USER_DATA / "verify_keep@example.com"
    conf = cfg._load_config()
    conf["profiles"] = {"verify_keep@example.com": str(keep)}
    cfg._save_config(conf)
    cfg.save_setting(bc.SETTING_KEY, "brave")
    cfg.auto_sync_profiles()
    if "verify_keep@example.com" not in cfg._load_config().get("profiles", {}):
        failures.append("profiles follow browser: the Brave scan unlinked a Chromium "  # noqa: F821
                        "account")

    # Add creates a directory instead of opening Brave's picker.
    add = inspect.getsource(ProfilesTab._on_add)
    if "CHROMIUM" not in add or "_on_add_chromium" not in add:
        failures.append("profiles follow browser: Add still opens Brave's profile "  # noqa: F821
                        "picker whatever the browser is")
    if "ensure_profile" not in inspect.getsource(ProfilesTab._on_add_chromium):
        failures.append("profiles follow browser: adding a Chromium profile does not "  # noqa: F821
                        "create its directory")
    scan = inspect.getsource(ProfilesTab._on_scan)
    if "auto_sync_profiles" not in scan:
        failures.append("profiles follow browser: Scan still reads Brave's Local State")  # noqa: F821
finally:
    for p in _made:
        shutil.rmtree(p, ignore_errors=True)
    conf = cfg._load_config()
    conf["profiles"] = _saved_profiles
    if _saved_browser is None:
        conf.pop(bc.SETTING_KEY, None)
    else:
        conf[bc.SETTING_KEY] = _saved_browser
    cfg._save_config(conf)

print("FAILED" if [f for f in failures if "profiles follow browser" in f] else "ok")  # noqa: F821
