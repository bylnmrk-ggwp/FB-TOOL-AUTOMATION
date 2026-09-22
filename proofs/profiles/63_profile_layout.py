"""Every way of opening a profile uses the same layout rule.

Brave keeps profiles inside one shared "User Data" tree and selects one with
--profile-directory. A Chromium profile IS its own user-data directory, and
the browser puts its data in a "Default" folder inside it.

start_browser learned that; extract_storage_state did not, and it is the one
the comment run uses. It opened the PARENT of the profile, captured a storage
state with no Facebook cookies at all, and every comment - including on
accounts that had just logged in - failed with "logged out or session
expired". One helper now answers the question for all of them.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("profile layout")  # noqa: F821

from src.core import browser_choice as bc  # noqa: E402
from src.core.facebook_automation import FacebookAutomation  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402

CHROMIUM_PROFILE = str(bc.CHROMIUM_USER_DATA / "someone@example.com")
BRAVE_PROFILE = str(bc.BRAVE_USER_DATA / "Profile 7")

_saved = cfg.get_setting(bc.SETTING_KEY, None)
try:
    cfg.save_setting(bc.SETTING_KEY, "chromium")
    user_data, profile_dir = FacebookAutomation._profile_layout(CHROMIUM_PROFILE)
    if user_data != CHROMIUM_PROFILE:
        failures.append(f"profile layout: a Chromium profile must be opened as its own "  # noqa: F821
                        f"user-data directory, got {user_data!r}")
    if profile_dir is not None:
        failures.append(f"profile layout: Chromium must get no --profile-directory, "  # noqa: F821
                        f"got {profile_dir!r}")

    cfg.save_setting(bc.SETTING_KEY, "brave")
    user_data, profile_dir = FacebookAutomation._profile_layout(BRAVE_PROFILE)
    if profile_dir != "Profile 7" or not user_data.endswith("User Data"):
        failures.append(f"profile layout: Brave must open its shared tree and select "  # noqa: F821
                        f"the profile, got {(user_data, profile_dir)}")
finally:
    if _saved is None:
        conf = cfg._load_config()
        conf.pop(bc.SETTING_KEY, None)
        cfg._save_config(conf)
    else:
        cfg.save_setting(bc.SETTING_KEY, _saved)

# No launch path may split the path by hand again - that is the bug.
for name in ("start_browser", "start_browser_headless", "extract_storage_state"):
    src = inspect.getsource(getattr(FacebookAutomation, name))
    if "_profile_layout" not in src:
        failures.append(f"profile layout: {name} does not use the shared layout rule")  # noqa: F821
    if "os.path.dirname(" in src:
        failures.append(f"profile layout: {name} still splits the profile path itself, "  # noqa: F821
                        f"which opens the wrong directory on Chromium")

# The storage state is what the comment run replays: capturing it from the
# wrong directory is what made every comment report a dead session.
extract = inspect.getsource(FacebookAutomation.extract_storage_state)
if "profile-directory" in extract and "if profile_dir_name else" not in extract:
    failures.append("profile layout: extraction passes --profile-directory "  # noqa: F821
                    "unconditionally, which is Brave's layout")

print("FAILED" if [f for f in failures if "profile layout" in f] else "ok")  # noqa: F821
