"""The recorded reason is what Facebook said, not a guess from the URL.

A re-login that fails already carries Facebook's own words - "Input Password
is invalid.", "Input Email or mobile number is invalid." - but the verdict
written to the database and the sheet came from _classify_account_access(),
which only looks at the final URL. Every one of those specific failures
landed as "LOGGED OUT OR SESSION EXPIRED", so a wrong password in the roster
was indistinguishable from an expired cookie and nobody knew to fix the
spreadsheet.

login_reason() maps the message; the URL classification stays the fallback
for the cases where the login never got far enough to produce one.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("login failure reason")  # noqa: F821

from src.core.driver_manager import login_reason  # noqa: E402

CASES = [
    ("Login failed: Input Password is invalid.", "wrong password"),
    ("Login failed: The password you've entered is incorrect.", "wrong password"),
    ("Login failed: Input Email or mobile number is invalid.", "bad username"),
    ("2FA / checkpoint required - finish it manually", "checkpoint"),
    ("2FA timed out after 120s", "needs 2FA"),
    ("Account has been disabled", "disabled"),
    ("signed in but never reached the home page - Facebook is gating this account",
     "no home page"),
    ("Failed to load login page: Page.goto: Target page, context or browser has been closed",
     "browser error - retry"),
]
for msg, want in CASES:
    got = login_reason(msg)
    if got != want:
        failures.append(f"login failure reason: {msg[:46]!r} -> {got!r}, wanted {want!r}")  # noqa: F821

# An unrecognised message falls through to whatever the URL said, not to a
# wrong guess.
if login_reason("something nobody has seen before") is not None:
    failures.append("login failure reason: an unknown message must return None so the "  # noqa: F821
                    "URL classification is used instead")
if login_reason("") is not None or login_reason(None) is not None:
    failures.append("login failure reason: empty input must return None")  # noqa: F821

# The re-login path has to consult it before falling back to the URL guess.
import inspect  # noqa: E402
from src.core.driver_manager import DriverManager  # noqa: E402
src = inspect.getsource(DriverManager._relogin_profile)
if "login_reason(" not in src:
    failures.append("login failure reason: _relogin_profile still records only the "  # noqa: F821
                    "URL classification, discarding Facebook's own message")

print("FAILED" if [f for f in failures if "login failure reason" in f] else "ok")  # noqa: F821
