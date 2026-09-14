"""A watch-only run opens the live immediately, with no batch in between.

A live has one edge and it moves. Sending a watch through the batch
machinery launched a shared browser, walked the profiles in fives and tore it
all down before the first page reached the stream - and the last profiles
joined minutes of broadcast later than the first. Both are removed: a queue
holding only watch items goes straight to _do_watch, and the pages open
together rather than in waves.
"""
import asyncio
import inspect
import queue as _queue
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("direct watch")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

URL = "https://www.facebook.com/share/v/19X6Eo7KTn/"
PROFILES = ["a@example.com", "b@example.com", "c@example.com"]

m = DriverManager()
logs = []
m.log = logs.append
m._fast_tests = True
opened_browser = []
m._create_temp_automation = lambda *a, **k: opened_browser.append("temp")
started = {}


async def _fake_watch(url, minutes=None, profile_names=None):
    started["url"] = url
    started["profiles"] = list(profile_names or [])
    started["after_batch"] = any("Starting batch" in line for line in logs)

m._do_watch = _fake_watch

items = [{"action_type": "watch", "profile_name": p, "post_url": URL,
          "watch_minutes": None} for p in PROFILES]
asyncio.run(m._do_batch(items))

if started.get("url") != URL or started.get("profiles") != PROFILES:
    failures.append(f"direct watch: the live was not opened: {started}")  # noqa: F821
if started.get("after_batch"):
    failures.append("direct watch: the run still went through the batch machinery "  # noqa: F821
                    "before reaching the live")
if opened_browser:
    failures.append("direct watch: a batch browser was launched for a watch-only "  # noqa: F821
                    "run")
if not any("Watching live directly" in line for line in logs):
    failures.append(f"direct watch: the log does not say it went straight to the "  # noqa: F821
                    f"live: {logs}")
events = []
while True:
    try:
        events.append(m.result_queue.get_nowait())
    except _queue.Empty:
        break
if not any(e.get("type") == "batch_result" for e in events):
    failures.append("direct watch: the UI is never told the run finished, so the "  # noqa: F821
                    "Run button stays disabled")
if m._batch_running:
    failures.append("direct watch: the run is still marked active after handing "  # noqa: F821
                    "over to the watch")

# Mixed queues keep their order: perform the actions, then stay to watch.
logs.clear()
started.clear()
mixed = [{"action_type": "react", "profile_name": PROFILES[0], "post_url": URL,
          "reaction": "like"}] + items
m2 = DriverManager()
m2.log = logs.append
m2._fast_tests = True
m2._do_watch = _fake_watch
batch_src = inspect.getsource(DriverManager._do_batch)
if "if watch_items and not items:" not in batch_src:
    failures.append("direct watch: the shortcut is not conditional on the queue "  # noqa: F821
                    "holding only watch items")

# Pages open together, not in waves of five.
watch_src = inspect.getsource(DriverManager._do_watch)
if "Semaphore(5)" in watch_src:
    failures.append("direct watch: the watch still opens five pages at a time, so "  # noqa: F821
                    "later profiles join the live late")

print("FAILED" if [f for f in failures if "direct watch" in f] else "ok")  # noqa: F821
