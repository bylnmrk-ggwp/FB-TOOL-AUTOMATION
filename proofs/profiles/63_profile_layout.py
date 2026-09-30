"""Every way of opening a profile uses the same layout rule.

Brave keeps profiles inside one shared "User Data" tree and selects one with
--profile-directory, so a saved profile path splits into the tree and the
folder name.

start_browser knew that; extract_storage_state did not, and it is the one the
comment run uses. It opened the wrong directory, captured a storage state with
no Facebook cookies at all, and every comment - including on accounts that had
just logged in - failed with "logged out or session expired". One helper now
answers the question for all of them, so a change to the rule cannot reach one
launch path and miss another.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("profile layout")  # noqa: F821

from src.core import browser_choice as bc  # noqa: E402
from src.core.facebook_automation import FacebookAutomation  # noqa: E402

BRAVE_PROFILE = str(bc.BRAVE_USER_DATA / "Profile 7")

user_data, profile_dir = FacebookAutomation._profile_layout(BRAVE_PROFILE)
if profile_dir != "Profile 7" or not user_data.endswith("User Data"):
    failures.append(f"profile layout: Brave must open its shared tree and select "  # noqa: F821
                    f"the profile, got {(user_data, profile_dir)}")

# No launch path may split the path by hand again - that is the bug.
for name in ("start_browser", "start_browser_headless", "extract_storage_state"):
    src = inspect.getsource(getattr(FacebookAutomation, name))
    if "_profile_layout" not in src:
        failures.append(f"profile layout: {name} does not use the shared layout rule")  # noqa: F821
    if "os.path.dirname(" in src:
        failures.append(f"profile layout: {name} still splits the profile path itself")  # noqa: F821

print("FAILED" if [f for f in failures if "profile layout" in f] else "ok")  # noqa: F821
