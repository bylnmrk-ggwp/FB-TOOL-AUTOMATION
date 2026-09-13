"""An unattended login does not sit out the 120 s 2FA wait.

login_with_credentials was written for the assisted desktop script: when
Facebook shows a checkpoint or 2FA page it waits up to 120 seconds for a
person to finish it in a visible window. The web app's login run drives a
HEADLESS browser with nobody watching, so that wait can only ever expire -
41 gated accounts meant 82 minutes of guaranteed failure, and the verdict
('2FA timed out after 120s') was the same one the immediate classification
gives. Unattended callers now get that verdict at once.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("unattended 2FA fast-fail")  # noqa: F821

from src.core import driver_manager as dm  # noqa: E402
from src.core.facebook_automation import FacebookAutomation  # noqa: E402

sig = inspect.signature(FacebookAutomation.login_with_credentials)
if "wait_for_2fa" not in sig.parameters:
    failures.append(  # noqa: F821
        f"login_with_credentials needs a wait_for_2fa switch, has {list(sig.parameters)}")
else:
    default = sig.parameters["wait_for_2fa"].default
    if default is not True:
        failures.append(  # noqa: F821
            f"wait_for_2fa must default to True so the assisted script keeps waiting, got {default!r}")

# The headless re-login path must opt out: it is the one with no human.
src = inspect.getsource(dm.DriverManager._relogin_profile)
if "wait_for_2fa=False" not in src:
    failures.append(  # noqa: F821
        "_relogin_profile must call login_with_credentials(..., wait_for_2fa=False): "
        "its browser is headless, so a 2FA wait can only time out")

# The assisted script still hands off to a person, so it must not opt out.
assisted = (ROOT / "scripts" / "login_accounts.py").read_text(encoding="utf-8")  # noqa: F821
if "wait_for_2fa=False" in assisted:
    failures.append("scripts/login_accounts.py must keep the 2FA wait - it opens a visible window")  # noqa: F821

# The body still has to contain the immediate verdict for the unattended case.
body = inspect.getsource(FacebookAutomation.login_with_credentials)
if "wait_for_2fa" not in body:
    failures.append("login_with_credentials ignores wait_for_2fa")  # noqa: F821

print("FAILED" if [f for f in failures if "2fa" in f.lower() or "_relogin_profile" in f] else "ok")  # noqa: F821
