"""The live viewer figure is read whatever wording Facebook used.

The heartbeat reported "Facebook shows no viewer count" on a watch where
19 of 19 pages were playing and the number was on the screen. The scraper
read ONLY aria-label attributes and required both "currently watching" and
the word "people" in the same label, so "328 viewers", "1.2K watching now"
and a figure rendered as plain text all came back as nothing.

The patterns live in Python and are handed to the page, so these are the
same expressions the browser runs - not a copy of them.
"""
import re
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("viewer count phrasings")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

PATTERNS = [re.compile(p, re.I) for p in DriverManager._WATCH_COUNT_PATTERNS]


def read(text: str) -> str | None:
    """What the page code would return for one string, patterns in order."""
    for pattern in PATTERNS:
        found = pattern.search(text)
        if found:
            return found.group(1).strip()
    return None


# Every wording Facebook has been seen to use, and what must come out of it.
READABLE = {
    "1.2K people are currently watching this live video.": "1.2K",
    "328 people are currently watching": "328",
    "1 person is currently watching": "1",
    "328 viewers are currently watching": "328",
    "1.2K viewers": "1.2K",
    "328 viewers": "328",
    "1.2K watching now": "1.2K",
    "328 watching": "328",
    "1.2K currently watching": "1.2K",
    "Watching now: 1.2K": "1.2K",
    "12,043 viewers": "12,043",
    "2.5M watching now": "2.5M",
    # The label this live actually served, kept as a fixture so a later
    # tightening cannot drop the wording Facebook is using right now.
    "3 people currently watching this video.": "3",
}
for label, want in READABLE.items():
    got = read(label)
    if got != want:
        failures.append(  # noqa: F821
            f"viewer count phrasings: {label!r} read as {got!r}, wanted {want!r}")

# A number next to any other word is not a viewer figure. The reaction and
# comment counts sit on the same page, so a looser pattern would report one
# of them as the audience.
NOT_A_COUNT = (
    "1.2K people reacted to this",
    "328 comments",
    "5 shares",
    "1.2K likes",
    "Like",
    "",
    # No digits at all. The trailing-number pattern used to match the full
    # stop here and report a viewer count of ".".
    "watching this video.",
    "Continue watching while you browse Facebook.",
)
for label in NOT_A_COUNT:
    got = read(label)
    if got is not None:
        failures.append(  # noqa: F821
            f"viewer count phrasings: {label!r} was read as a viewer count "
            f"({got!r}), so the heartbeat would publish the wrong number")

# The page code has to look past aria-label, which is what it only did
# before, and it has to be given the patterns rather than holding its own.
js = DriverManager._WATCH_VIEWERS_JS
if "textContent" not in js:
    failures.append("viewer count phrasings: the page code still reads only "  # noqa: F821
                    "aria-label, so a count rendered as plain text is missed")
if "(patterns) =>" not in js:
    failures.append("viewer count phrasings: the page code does not take the "  # noqa: F821
                    "patterns, so what this proof tests is not what runs")
if "currently watching/i.test" in js:
    failures.append("viewer count phrasings: a label still has to say "  # noqa: F821
                    "'currently watching' before it is looked at")

import inspect  # noqa: E402
call = inspect.getsource(DriverManager._facebook_viewer_count)
if "_WATCH_COUNT_PATTERNS" not in call:
    failures.append("viewer count phrasings: the patterns are never passed to "  # noqa: F821
                    "the page, so the call raises or matches nothing")

print("FAILED" if [f for f in failures if "viewer count phrasings" in f] else "ok")  # noqa: F821
