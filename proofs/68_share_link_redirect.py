"""A /share/ link resolving to a permalink is not a hijacked navigation.

Facebook exchanges every /share/p/<token>/ link for the post's permalink and
appends rdid, its own redirect token. The reaction path warned "Facebook
added redirect parameter!" on every one of them, then tried to verify the
post identity against a URL that carries no identity at all - a share token
has no story_fbid, no /posts/<id>, no profile id - so an ordinary share link
looked like a redirect to the wrong post.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("share link redirect")  # noqa: F821

from src.core.facebook_automation import FacebookAutomation, _without_tracking  # noqa: E402

PERMALINK = "https://www.facebook.com/jed.m/posts/pfbid0bN3"

# Tracking is stripped; the post identity is not.
got = _without_tracking(PERMALINK + "?rdid=Qt2UTwwzxrRGba29&mibextid=abc")
if got != PERMALINK:
    failures.append(f"share link redirect: tracking not stripped cleanly: {got!r}")  # noqa: F821
keeps_id = _without_tracking(
    "https://www.facebook.com/permalink.php?story_fbid=123&id=456&__tn__=x")
if "story_fbid=123" not in keeps_id or "id=456" not in keeps_id:
    failures.append(f"share link redirect: stripping removed the post identity: "  # noqa: F821
                    f"{keeps_id!r}")
untouched = "https://www.facebook.com/share/p/1EmKKhWSaR/"
if _without_tracking(untouched) != untouched:
    failures.append("share link redirect: a clean URL was rewritten")  # noqa: F821

src = inspect.getsource(FacebookAutomation)
if "WARNING: Facebook added redirect parameter" in src:
    failures.append("share link redirect: rdid is still reported as a hijacked "  # noqa: F821
                    "navigation, which it never was")

react = None
for name in dir(FacebookAutomation):
    if "react" in name.lower():
        try:
            body = inspect.getsource(getattr(FacebookAutomation, name))
        except Exception:
            continue
        if "expected_story_fbid" in body:
            react = body
            break
if react is None:
    failures.append("share link redirect: the reaction path no longer verifies the "  # noqa: F821
                    "post it landed on")
else:
    if '"/share/" in post_url' not in react:
        failures.append("share link redirect: a share link is still checked against "  # noqa: F821
                        "identifiers it cannot carry")
    if "_without_tracking(current_url)" not in react:
        failures.append("share link redirect: the landed URL is compared with its "  # noqa: F821
                        "tracking parameters still attached")

print("FAILED" if [f for f in failures if "share link redirect" in f] else "ok")  # noqa: F821
