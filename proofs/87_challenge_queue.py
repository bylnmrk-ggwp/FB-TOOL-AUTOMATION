"""The accounts waiting on a person are worked as one queue.

Two of five accounts in a live run came back needing a captcha and two more
needing a 2FA code. Both are verdicts where Facebook has already ACCEPTED the
password and the only missing thing is a human. Reaching them again meant
re-running the roster and sitting through every other account to get there -
and each of those attempts is another failed login against an account
Facebook is already gating, which is the one thing that makes the gating
worse.

So --challenges walks only those accounts. The queue is read from
accounts.status_reason, which the previous run already wrote; nothing new is
stored, and no second source of truth can drift from the first.

What has to stay true:

  1. a 2FA prompt and a captcha are queued - the operator can clear both
  2. nothing else is, especially the verdicts a person CANNOT fix at the
     keyboard (a disabled account, a wrong password, a bad username)
  3. the queue's reasons are derived from short_reason(), so re-wording a
     reason moves the queue with it instead of silently emptying it
  4. --challenges turns the hand-off on by itself, since a queue of
     challenges nobody is asked to answer would just fail them all again
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT
sys.path.insert(0, str(ROOT / "scripts"))  # noqa: F821

step("challenge queue")  # noqa: F821

import login_accounts as la  # noqa: E402


def _fail(msg):
    failures.append(f"challenge queue: {msg}")  # noqa: F821


def _acct(username, reason, status=""):
    return {"username": username, "status_reason": reason, "status": status,
            "linked_profile": username}


# 3. Derived, not typed out. If short_reason() is re-worded and the queue is
#    not, the queue matches nothing and quietly reports "nothing is blocked".
reasons = la.challenge_reasons()
if reasons != {la.short_reason(la.NEEDS_2FA).lower(),
               la.short_reason(la.NEEDS_CAPTCHA).lower()}:
    _fail(f"the queue's reasons {reasons} are not the ones short_reason() "
          f"writes, so a re-worded reason would empty the queue")
if len(reasons) != 2 or "" in reasons:
    _fail(f"expected two distinct non-empty reasons, got {reasons}")

# 1 + 2. Exactly the two clearable verdicts, and nothing else.
roster = [
    _acct("twofa@x", la.short_reason(la.NEEDS_2FA)),
    _acct("captcha@x", la.short_reason(la.NEEDS_CAPTCHA)),
    _acct("shouty@x", la.short_reason(la.NEEDS_CAPTCHA).upper()),   # case
    _acct("padded@x", f"  {la.short_reason(la.NEEDS_2FA)}  "),      # whitespace
    _acct("fine@x", "", status="ok"),
    _acct("nopass@x", la.short_reason(la.BAD_PASSWORD)),
    _acct("noname@x", la.short_reason(la.BAD_IDENTIFIER)),
    _acct("dead@x", la.short_reason(la.DISABLED), status="disabled"),
    _acct("slow@x", "timeout - retry"),
    _acct("broke@x", "browser error - retry"),
    _acct("blank@x", ""),
    _acct("none@x", None),
]
queued = {a["username"] for a in la.challenge_queue(roster)}

for want in ("twofa@x", "captcha@x", "shouty@x", "padded@x"):
    if want not in queued:
        _fail(f"{want} waits on a person and was not queued")
for never in ("fine@x", "nopass@x", "noname@x", "dead@x", "slow@x",
              "broke@x", "blank@x", "none@x"):
    if never in queued:
        _fail(f"{never} was queued, but sitting at the keyboard cannot "
              f"clear it - that is a wasted login attempt against an "
              f"account Facebook is already gating")

# An empty roster is a legitimate answer, not a crash.
if la.challenge_queue([]) != []:
    _fail("an empty roster did not produce an empty queue")

# 4. The mode has to ask the operator, or it just re-fails every account.
_main = inspect.getsource(la.main)
if "args.challenges" not in _main:
    _fail("main() never looks at --challenges")
else:
    head = _main[_main.find("args.challenges"):]
    if "hand_off_2fa = True" not in head[:400]:
        _fail("--challenges does not turn the hand-off on, so a queue of "
              "challenges would run with nobody being asked to answer them")

print("FAILED" if [f for f in failures if "challenge queue" in f] else "ok")  # noqa: F821
