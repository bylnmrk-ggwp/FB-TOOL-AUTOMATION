"""A normal login step is not a checkpoint, and an unattended run waits
briefly before calling one.

Facebook walks a successful login through
`/login/device-based/regular/login/`. That substring sat in the
checkpoint keyword list, so when the unattended path stopped waiting
120 s for a human it began reporting ordinary logins as
"2FA / checkpoint required" - accounts the operator could sign into by
hand came back NOT LOGGED IN / CHECKPOINT OR VERIFICATION REQUIRED.

Two rules follow:
  * the keyword list names only real gates, never a step of the ordinary
    flow;
  * an unattended caller still gives the page a short grace period to
    leave a gate URL on its own, rather than judging the first frame it
    sees. It just does not wait the full human-sized 120 s.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("login gate detection")  # noqa: F821

from src.core.facebook_automation import FacebookAutomation  # noqa: E402

_raw = inspect.getsource(FacebookAutomation.login_with_credentials)
# Comments explain WHY a string is not a gate, so they mention it; judge the
# code only.
src = chr(10).join(l for l in _raw.splitlines() if not l.lstrip().startswith("#"))

# The ordinary login redirect must not be treated as a gate.
if "login/device-based" in src:
    failures.append(  # noqa: F821
        "login gate: 'login/device-based' is a normal login redirect, not a checkpoint - "
        "matching it reports successful logins as gated")
# "review" as a bare substring matches far more than a checkpoint page.
if '"review"' in src or "'review'" in src:
    failures.append(  # noqa: F821
        "login gate: bare 'review' is too loose a substring for a gate test")

# The real gates must still be detected.
for gate in ("checkpoint", "twofactor", "two_step_verification"):
    if gate not in src:
        failures.append(f"login gate: stopped detecting {gate!r}")  # noqa: F821

# Unattended must poll for a grace period, not return on the first frame.
if "UNATTENDED_GATE_GRACE_S" not in src:
    failures.append(  # noqa: F821
        "login gate: unattended path must wait UNATTENDED_GATE_GRACE_S for the page "
        "to leave the gate before declaring one")
grace = getattr(FacebookAutomation, "UNATTENDED_GATE_GRACE_S", None)
if not isinstance(grace, (int, float)):
    failures.append("login gate: FacebookAutomation.UNATTENDED_GATE_GRACE_S missing")  # noqa: F821
elif not (5 <= grace <= 45):
    failures.append(  # noqa: F821
        f"login gate: grace of {grace}s is outside the useful 5-45 s band - "
        "long enough to clear a redirect, far short of the 120 s human wait")

# The assisted 120 s hand-off stays for a visible window.
if "120" not in src:
    failures.append("login gate: the assisted 120 s wait was lost")  # noqa: F821

print("FAILED" if [f for f in failures if "login gate" in f] else "ok")  # noqa: F821
