"""A sheet the PC cannot reach backs off and says so in one line.

The watcher polled every 20s whatever happened, and a DNS failure printed
urllib3's three nested exceptions each time: "TransportError:
HTTPSConnectionPool(host='oauth2.googleapis.com', port=443): Max retries
exceeded with url: /token (Caused by NameResolutionError(...". A PC that
loses its network answers every poll that way, so the log filled with the
same 200 characters and the sheet was hit uselessly for as long as the
outage lasted.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("sheet offline")  # noqa: F821

from src.storage.roster_sheet import SheetWatcher, _reason  # noqa: E402

# A name-resolution failure reads as being offline, not as a stack of URLs.
dns = Exception("HTTPSConnectionPool(host='oauth2.googleapis.com', port=443): "
                "Max retries exceeded with url: /token (Caused by "
                "NameResolutionError(\"...Failed to resolve 'oauth2.googleapis.com'\"))")
said = _reason(dns)
if "offline" not in said:
    failures.append(f"sheet offline: a DNS failure is not reported as being "  # noqa: F821
                    f"offline: {said!r}")
if len(said) > 60:
    failures.append(f"sheet offline: the message is still a dump ({len(said)} chars)")  # noqa: F821
# An error that is NOT a network failure keeps its own words.
other = _reason(ValueError("Sheet needs a USERNAME header"))
if "offline" in other or "USERNAME" not in other:
    failures.append(f"sheet offline: a real error was flattened into 'offline': {other!r}")  # noqa: F821

# The wait grows while failing and returns to normal on success.
w = SheetWatcher(interval=20)
if w._retry_wait() != 20:
    failures.append(f"sheet offline: a healthy watcher should poll every 20s, "  # noqa: F821
                    f"got {w._retry_wait()}")
waits = []
for _ in range(6):
    w._failures += 1
    waits.append(w._retry_wait())
if waits != sorted(waits) or waits[0] >= waits[-1]:
    failures.append(f"sheet offline: the retry wait does not grow: {waits}")  # noqa: F821
if waits[-1] > w.MAX_BACKOFF:
    failures.append(f"sheet offline: the wait passed the cap: {waits[-1]}")  # noqa: F821
w._failures = 0
if w._retry_wait() != 20:
    failures.append("sheet offline: the wait did not return to normal after a "  # noqa: F821
                    "successful poll")

print("FAILED" if [f for f in failures if "sheet offline" in f] else "ok")  # noqa: F821
