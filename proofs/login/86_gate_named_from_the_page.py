"""A gate is named from what the page shows, not from its URL.

Every one of five accounts came back as "credentials accepted, needs a 2FA
code", and three of them had no 2FA to answer: what was on screen was an
"I am not a robot" box. Facebook serves that box ON the
two_step_verification page - the login log recorded
recaptcha/enterprise/anchor and bframe frames at exactly that URL - and the
gate was named by matching "two_step_verification" in the path. So a captcha
was announced as a missing authenticator code, the run never tried to tick
the box, and the operator was sent looking for a code that does not exist.

The fix is ordering: on a gate URL, ask the page whether a captcha is there
and try to clear it FIRST, then name whatever is left. Four things have to
stay true for that to hold.

  1. the captcha check runs before the gate is named
  2. clearing it re-reads the URL, so the naming judges where the page is
     now rather than where it was
  3. the verdict survives the SECOND classifier in scripts/login_accounts.py,
     which re-named it from the URL on its way to the summary and the sheet
  4. the check waits for the captcha to load, because it arrives in iframes
     the gate page fetches after it settles

Source-level, like proofs/62. The gate sits in the middle of
login_with_credentials, after a real form has been filled on a real
Facebook page, so there is no way to reach it here without logging in to
Facebook - which a proof must never do.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("gate named from the page")  # noqa: F821

from src.core.facebook_automation import FacebookAutomation  # noqa: E402


def _fail(msg):
    failures.append(f"gate naming: {msg}")  # noqa: F821


src = inspect.getsource(FacebookAutomation.login_with_credentials)

naming = src.find("gate = (")
if naming < 0:
    _fail("login_with_credentials no longer names the gate; this proof is "
          "watching the wrong place")
else:
    # The page has to be asked before anything is named.
    asked = src.find("_captcha_appears")
    if asked < 0:
        _fail("the gate is named without ever asking the page whether a "
              "captcha is on it")
    elif asked > naming:
        _fail("the captcha check happens AFTER the gate is named, so a "
              "captcha is still reported as a missing 2FA code")

    handling = src.find("handle_recaptcha", 0, naming)
    if handling < 0:
        _fail("a gate page carrying a captcha is never given to "
              "handle_recaptcha, so the box is never ticked")

    # Clearing a captcha moves the page. Naming the gate from the URL read
    # before that would report the gate the account has already passed.
    reread = src.find("current_url = self.page.url.lower()", handling if handling >= 0 else 0)
    if not (0 <= reread < naming):
        _fail("the URL is not re-read after the captcha is handled, so a "
              "cleared gate is still reported as a gate")

# A captcha verdict must not be reported with 2FA wording, or the fix is
# invisible to whoever reads the summary.
if "captcha - solve it in the window" not in src:
    _fail("there is no captcha-specific verdict; a captcha would be folded "
          "back into the 2FA message")


# The run script classifies a second time, for the summary and the sheet, and
# it used to key on the URL alone as well - so the automation's captcha
# verdict was overwritten with "needs a 2FA code" on the way out. A captcha
# has to survive both classifiers to reach the operator.
sys.path.insert(0, str(ROOT / "scripts"))  # noqa: F821
import login_accounts as la  # noqa: E402

GATE = "https://www.facebook.com/two_step_verification/authentication/?x=1"

verdict = la.classify(GATE, "captcha - solve it in the window")
if verdict != la.NEEDS_CAPTCHA:
    _fail(f"a captcha on the two_step_verification page classifies as "
          f"{verdict!r}, not a captcha")
if la.short_reason(la.NEEDS_CAPTCHA) == la.short_reason(la.NEEDS_2FA):
    _fail("a captcha and a 2FA prompt write the same status, so the sheet "
          "cannot tell them apart")

# A real 2FA prompt on the same URL must still read as 2FA: the fix must not
# turn every gate into a captcha.
if la.classify(GATE, "two-factor authentication required - finish it "
                     "manually") != la.NEEDS_2FA:
    _fail("a genuine 2FA gate no longer classifies as 2FA")


# reCAPTCHA arrives in iframes the gate page loads after it settles, so the
# check has to wait rather than judge the first instant. Account 4 of a live
# five-account run proved it: the log listed recaptcha anchor and bframe
# frames on the page and the run still called it a missing 2FA code, because
# nothing had loaded yet when the single check ran.
appear = inspect.getsource(FacebookAutomation._captcha_appears)
if "sleep" not in appear:
    _fail("_captcha_appears does not wait, so a captcha that loads a moment "
          "late is reported as a 2FA prompt")
if FacebookAutomation.CAPTCHA_APPEAR_S < 2:
    _fail(f"CAPTCHA_APPEAR_S is {FacebookAutomation.CAPTCHA_APPEAR_S}s, too "
          f"short for an iframe to load")

print("FAILED" if [f for f in failures if "gate naming" in f] else "ok")  # noqa: F821
