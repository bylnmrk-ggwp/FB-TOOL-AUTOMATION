"""A watcher that dies mid-broadcast is rebuilt, not abandoned.

"Stay until the live ends" fails quietly when a page dies: a crashed
renderer or a closed context answered nothing, the keeper skipped it, and
that profile left the broadcast without a word. The watch went on looking
healthy with fewer and fewer viewers.

A page that cannot be asked anything is rebuilt from the storage state it was
opened with, on the live it was watching. A page that keeps dying is a dead
session rather than a blip, so the rebuilding is bounded.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("watch to the end")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

URL = "https://www.facebook.com/share/v/live/"

keeper = inspect.getsource(DriverManager._keep_watching)
if "_revive_watcher" not in keeper:
    failures.append("watch to the end: a page that stops answering is skipped, so "  # noqa: F821
                    "that profile silently leaves the live")

watch = inspect.getsource(DriverManager._do_watch)
if "_watch_states" not in watch:
    failures.append("watch to the end: the storage state is not kept, so a dead "  # noqa: F821
                    "page cannot be rebuilt")

if not (1 <= DriverManager.WATCH_REVIVE_LIMIT <= 10):
    failures.append(f"watch to the end: the rebuild limit is "  # noqa: F821
                    f"{DriverManager.WATCH_REVIVE_LIMIT}, which either gives up at "
                    f"once or never stops")


class _Page:
    def __init__(self):
        self.url = URL

    async def goto(self, url, **kw):
        return None


class _Auto:
    def __init__(self):
        self.page = _Page()

    async def close_context(self):
        return None

    async def init_from_storage(self, browser, state, **kw):
        return None


m = DriverManager()
m.log = lambda message: None
m._watch_browser = object()
m._watch_urls = {"a": URL}
m._watch_states = {"a": {"cookies": []}}
m._watch_autos = {"a": _Auto()}
m._watch_revivals = {}

import src.core.facebook_automation as fa  # noqa: E402
_real = fa.FacebookAutomation
fa.FacebookAutomation = lambda *a, **k: _Auto()
try:
    if not asyncio.run(m._revive_watcher("a")):
        failures.append("watch to the end: a dead page was not rebuilt")  # noqa: F821
    if "a" not in m._watch_autos:
        failures.append("watch to the end: the rebuilt page is not back in the watch")  # noqa: F821

    # Bounded: a page that keeps dying is eventually left alone.
    for _ in range(DriverManager.WATCH_REVIVE_LIMIT + 2):
        asyncio.run(m._revive_watcher("a"))
    if m._watch_revivals.get("a", 0) > DriverManager.WATCH_REVIVE_LIMIT:
        failures.append("watch to the end: rebuilding never stops, so a dead "  # noqa: F821
                        "session would be reopened forever")

    # Nothing to rebuild from is not a rebuild.
    m._watch_states.pop("a", None)
    m._watch_revivals.clear()
    if asyncio.run(m._revive_watcher("a")):
        failures.append("watch to the end: a page was 'rebuilt' with no stored "  # noqa: F821
                        "session")
finally:
    fa.FacebookAutomation = _real

print("FAILED" if [f for f in failures if "watch to the end" in f] else "ok")  # noqa: F821
