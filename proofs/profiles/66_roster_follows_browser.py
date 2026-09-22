"""Account search offers only accounts this browser can connect to.

The roster listed every account whatever browser its profile belonged to, so
with Brave selected the search returned accounts whose only profile is a
Chromium directory Brave cannot open - each one a link that leads to a run
that cannot start. Accounts with no profile at all stay listed: those are the
ones the operator links next.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("roster follows browser")  # noqa: F821

from src.ui.profiles_tab import ProfilesTab  # noqa: E402

render = inspect.getsource(ProfilesTab._render_roster)
if "list_profiles_for_browser" not in render:
    failures.append("roster follows browser: the roster still lists accounts of "  # noqa: F821
                    "both browsers, so a search offers profiles this one cannot open")
if "linked_profile" not in render:
    failures.append("roster follows browser: the filter does not look at what the "  # noqa: F821
                    "account is linked to")

# An unlinked account must survive the filter - it is the one you link next.
import re  # noqa: E402
kept_unlinked = re.search(r"not \(a\.get\(\"linked_profile\"\) or \"\"\)", render)
if not kept_unlinked:
    failures.append("roster follows browser: an account with no profile is filtered "  # noqa: F821
                    "out, so it can never be linked")

# Linking offers this browser's profiles only.
picker = inspect.getsource(ProfilesTab._pick_saved_profile)
if "list_profiles_for_browser" not in picker:
    failures.append("roster follows browser: the link picker still offers the other "  # noqa: F821
                    "browser's profiles")

# Listing profiles must not consult login state at all: the list answers
# "what profiles are there", and Check Login Status answers the other
# question on demand instead of on every refresh.
for name, source in (("_visible_profiles", inspect.getsource(ProfilesTab._visible_profiles)),):
    if "logged_in_profiles" in source:
        failures.append(f"roster follows browser: {name} still fetches login state")  # noqa: F821

from src.ui.queue_tab import QueueTab  # noqa: E402
if "logged_in_profiles" in inspect.getsource(QueueTab._refresh_profile_status):
    failures.append("roster follows browser: the queue count still fetches login "  # noqa: F821
                    "state on every refresh")

print("FAILED" if [f for f in failures if "roster follows browser" in f] else "ok")  # noqa: F821
