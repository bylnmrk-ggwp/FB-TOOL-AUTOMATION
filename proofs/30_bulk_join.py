"""Proof (BUG 1): bulk join must join EVERY url, not only the last one.

_do_join_group_bulk's inner _join_one loops over the group urls. The join,
the db.record_join, the join_group_item_result emit and the inter-url delay
must run once per url INSIDE that loop. The bug left them dedented to the
loop's own level, so they ran a single time after the loop on the last url.

No browser, no Google, no real Brave dir: async_playwright and
FacebookAutomation are stubbed, cfg/db are monkeypatched, and the manager's
own worker thread is never started (we await the handler directly).
"""
import asyncio
import queue as _q
import sys

sys.path.insert(0, str(ROOT))

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.core import driver_manager as _dm  # noqa: E402
from src.core import facebook_automation as _fa  # noqa: E402

step("bulk join joins every url")

_JOIN_CALLS = []


class _FakeAuto:
    def __init__(self, *a, **k):
        pass

    async def init_from_storage(self, *a, **k):
        return None

    async def go_to_facebook(self):
        return None

    async def _is_logged_in(self, timeout=15):
        return True

    async def join_group(self, url):
        _JOIN_CALLS.append(url)
        return True, "joined"

    async def close_context(self):
        return None

    async def extract_storage_state(self, brave_path):
        return {"cookies": []}


class _FakeBrowser:
    async def close(self):
        return None


class _FakeChromium:
    async def launch(self, **k):
        return _FakeBrowser()


class _FakePW:
    def __init__(self):
        self.chromium = _FakeChromium()

    async def stop(self):
        return None


class _FakeStarter:
    async def start(self):
        return _FakePW()


def _fake_async_playwright():
    return _FakeStarter()


# ---- save originals so the module is left exactly as found -----------------
_orig = {
    "async_playwright": _dm.async_playwright,
    "fa_FacebookAutomation": _fa.FacebookAutomation,
    "get_profile_path": _dm.cfg.get_profile_path,
    "get_share_delays": _dm.cfg.get_share_delays,
    "has_joined": _dm.db.has_joined,
    "record_join": _dm.db.record_join,
    "log_activity": _dm.db.log_activity,
}

try:
    _dm.async_playwright = _fake_async_playwright
    _fa.FacebookAutomation = _FakeAuto
    _dm.cfg.get_profile_path = lambda name: "C:/fake/brave/dir"
    _dm.cfg.get_share_delays = lambda: {
        "join_backoff_min": 0, "join_backoff_max": 0,
        "join_retry_min": 0, "join_retry_max": 0,
        "between_joins_min": 0, "between_joins_max": 0,
        "between_shares_min": 0, "between_shares_max": 0,
    }
    _dm.db.has_joined = lambda profile, url: False
    _dm.db.record_join = lambda *a, **k: None
    _dm.db.log_activity = lambda *a, **k: None

    _m = _DM(log_callback=lambda msg: None)
    _m._create_temp_automation = lambda: _FakeAuto()

    _urls = ["https://facebook.com/groups/AAA", "https://facebook.com/groups/BBB"]
    asyncio.run(_m._do_join_group_bulk({
        "type": "join_group_bulk",
        "group_urls": _urls,
        "profile_names": ["VERIFYP1"],
    }))

    # collect emitted events
    _items = []
    while True:
        try:
            _ev = _m.result_queue.get_nowait()
        except _q.Empty:
            break
        if _ev.get("type") == "join_group_item_result":
            _items.append(_ev)

    if len(_JOIN_CALLS) != 2:
        failures.append(
            f"bulk join: join_group called {len(_JOIN_CALLS)} time(s), expected 2 "
            f"(calls={_JOIN_CALLS})")
    if len(_items) != 2:
        failures.append(
            f"bulk join: emitted {len(_items)} join_group_item_result event(s), expected 2")
finally:
    _dm.async_playwright = _orig["async_playwright"]
    _fa.FacebookAutomation = _orig["fa_FacebookAutomation"]
    _dm.cfg.get_profile_path = _orig["get_profile_path"]
    _dm.cfg.get_share_delays = _orig["get_share_delays"]
    _dm.db.has_joined = _orig["has_joined"]
    _dm.db.record_join = _orig["record_join"]
    _dm.db.log_activity = _orig["log_activity"]

print("ok" if not [f for f in failures if f.startswith("bulk join")] else "FAILED")
