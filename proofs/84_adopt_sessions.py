"""A profile signed in by hand is part of the fleet too.

122 browser profiles held a Facebook session; 49 had an account row. The
other 73 were invisible to every roster query - never counted as active,
never kept warm - so their sessions were left to expire while the tool
reported a fleet a third of its real size. The sweep now visits a profile
that has a session but no row, and adopts it the moment the session proves
itself.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("adopt sessions")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402
from src.storage import database as db  # noqa: E402

ORPHAN = "verify_orphan_profile"

try:
    db._get_conn().execute("DELETE FROM accounts WHERE username = ?", (ORPHAN,))
    db._get_conn().commit()

    if db.account_for_profile(ORPHAN) is not None:
        failures.append("adopt sessions: the test profile started out linked")  # noqa: F821

    if not db.adopt_profile(ORPHAN):
        failures.append("adopt sessions: a signed-in profile with no account row "  # noqa: F821
                        "was not given one")
    account = db.account_for_profile(ORPHAN)
    if not account:
        failures.append("adopt sessions: adoption reported success but left no "  # noqa: F821
                        "account linked to the profile")
    # Adopted accounts carry no password: nothing may try to log one in.
    if db.credentials_for_profile(ORPHAN) is not None:
        failures.append("adopt sessions: an adopted account offers credentials, so "  # noqa: F821
                        "a re-login would be attempted with a password nobody set")
    # Adoption is once. A second call must not create a second row.
    if db.adopt_profile(ORPHAN):
        failures.append("adopt sessions: adopting twice made a second row")  # noqa: F821

    # Once recorded as logged in, the profile counts as active.
    db.record_login_check(ORPHAN, True)
    if ORPHAN not in db.logged_in_profiles():
        failures.append("adopt sessions: an adopted profile with a live session is "  # noqa: F821
                        "still not counted as logged in")
finally:
    db._get_conn().execute("DELETE FROM accounts WHERE username = ?", (ORPHAN,))
    db._get_conn().commit()

# The sweep has to actually reach those profiles.
sweep = inspect.getsource(DriverManager._session_sweep)
if "account_for_profile" not in sweep:
    failures.append("adopt sessions: the sweep visits only profiles that already "  # noqa: F821
                    "have an account row, so an orphan is never found")
if "list_profiles_for_browser" not in sweep:
    failures.append("adopt sessions: the sweep ignores the machine share, so every "  # noqa: F821
                    "PC in a split fleet warms the same accounts")

keepalive = inspect.getsource(DriverManager._keepalive_profile)
if "adopt_profile" not in keepalive:
    failures.append("adopt sessions: a proven session is never adopted")  # noqa: F821
if "_record_and_publish(profile_name, True" not in keepalive:
    failures.append("adopt sessions: a session proven live is not recorded as such, "  # noqa: F821
                    "so an adopted account stays inactive")

# The pass is bounded, and rotates: a sweep that ran the whole fleet would
# hold the machine for an hour, and one that always took the first few would
# starve the rest.
manager = DriverManager.__new__(DriverManager)
names = [f"p{i:03d}" for i in range(30)]
first = DriverManager._sweep_slice(manager, names)
second = DriverManager._sweep_slice(manager, names)
if len(first) > DriverManager.SWEEP_BATCH:
    failures.append(f"adopt sessions: one pass visits {len(first)} profiles, which "  # noqa: F821
                    f"is the whole fleet in one go")
if first == second:
    failures.append("adopt sessions: every pass visits the same profiles, so the "  # noqa: F821
                    "rest are never kept warm")
short = ["a", "b"]
if DriverManager._sweep_slice(manager, short) != short:
    failures.append("adopt sessions: a fleet smaller than one slice is not visited "  # noqa: F821
                    "whole")

print("FAILED" if [f for f in failures if "adopt sessions" in f] else "ok")  # noqa: F821
