"""A page is not called dead for being slow to start its player.

`_verify_watching` gives a freshly opened page WATCH_VERIFY_TIMEOUT_MS to
mount a <video>. Pages opened together starve each other's decoder for much
longer than that, so the first pass rejects healthy pages - measured on
three real lives:

    reported 6/12   kick found players on 11
    reported 9/12   kick found players on 12
    reported 8/30   kick found players on 26

all 22 of those 30 rejections said "no video player on the page", and not
one was a login gate. The operator was told the fleet was broken while 26
accounts watched the broadcast.

`_WATCH_KICK_JS` returns false when there is no <video>, so the live-edge
pass that runs straight after the verdicts already proves which pages have
a player. The rejected ones are re-judged against that.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("no page is judged too early")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

watch = inspect.getsource(DriverManager._do_watch)

# The re-judge has to come AFTER the kick, or it is just the first pass
# again with a shorter timeout and would reject even more.
try:
    kick_at = watch.index("_WATCH_KICK_JS")
    late_at = watch.index('if v == "no video player on the page"')
except ValueError:
    kick_at = late_at = -1
    failures.append("no page is judged too early: the watch never re-judges "  # noqa: F821
                    "the pages it rejected, so a slow player is recorded as "
                    "an account that is not watching")
if kick_at >= 0 and late_at >= 0 and late_at < kick_at:
    failures.append("no page is judged too early: the re-judge runs before the "  # noqa: F821
                    "live-edge kick, so it has no new evidence to judge on")

# It must re-judge only the rejected pages. Re-running every page would
# spend WATCH_VERIFY_SAMPLE_SECONDS on pages already known to be playing.
if 'v == "playing"' in watch and "late = [" in watch:
    late_block = watch[watch.index("late = ["):watch.index("late = [") + 240]
    if "no video player on the page" not in late_block:
        failures.append("no page is judged too early: the re-judge is not "  # noqa: F821
                        "limited to the pages that were rejected")

# A re-judge must not wait the full first-pass timeout again.
if not hasattr(DriverManager, "WATCH_RECHECK_SETTLE_MS"):
    failures.append("no page is judged too early: there is no shorter wait for "  # noqa: F821
                    "the re-judge, so it costs the full timeout per page")
elif DriverManager.WATCH_RECHECK_SETTLE_MS >= DriverManager.WATCH_VERIFY_TIMEOUT_MS:
    failures.append(  # noqa: F821
        f"no page is judged too early: the re-judge waits "
        f"{DriverManager.WATCH_RECHECK_SETTLE_MS}ms, no less than the first "
        f"pass's {DriverManager.WATCH_VERIFY_TIMEOUT_MS}ms")

# ── The shorter wait is really honoured ──
verify = inspect.signature(DriverManager._verify_watching)
if "settle_ms" not in verify.parameters:
    failures.append("no page is judged too early: _verify_watching takes no "  # noqa: F821
                    "shorter wait, so the re-judge cannot ask for one")
else:
    asked = {}

    class _Page:
        url = "https://www.facebook.com/"

        async def evaluate(self, *a, **k):
            return False          # no login gate

        async def wait_for_selector(self, selector, timeout=None):
            asked["timeout"] = timeout
            raise RuntimeError("no video")   # the path under test

    class _Auto:
        page = _Page()

    manager = DriverManager()
    manager.log = lambda message: None
    verdict = asyncio.run(
        manager._verify_watching(_Auto(), "whoever", settle_ms=1234))
    if asked.get("timeout") != 1234:
        failures.append(f"no page is judged too early: settle_ms was ignored - "  # noqa: F821
                        f"the selector waited {asked.get('timeout')!r}")
    if verdict != "no video player on the page":
        failures.append(f"no page is judged too early: a page with no player "  # noqa: F821
                        f"was judged {verdict!r}")

    # Default still uses the long first-pass timeout.
    asked.clear()
    asyncio.run(manager._verify_watching(_Auto(), "whoever"))
    if asked.get("timeout") != DriverManager.WATCH_VERIFY_TIMEOUT_MS:
        failures.append(f"no page is judged too early: the first pass no longer "  # noqa: F821
                        f"waits WATCH_VERIFY_TIMEOUT_MS - it waited "
                        f"{asked.get('timeout')!r}")

print("FAILED" if [f for f in failures  # noqa: F821
                   if "no page is judged too early" in f] else "ok")
