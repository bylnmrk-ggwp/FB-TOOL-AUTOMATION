"""Watch keeps the profiles on the post after the run, instead of being an
item that is performed and closed.

React and comment finish and their contexts close. A viewer does not: the
page has to stay open with the video playing. So a watch queued alongside
them is pulled out of the item list and started when the batch is done, with
exactly the profiles that were asked to watch.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("watch after batch")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402
from src.ui.queue_tab import QueueTab  # noqa: E402

URL = "https://www.facebook.com/share/p/1Ecv3uHm2A/"
PROFILES = ["a@example.com", "b@example.com"]

# The queue offers it next to React and Comment.
build = inspect.getsource(QueueTab._build_ui)
if "_feat_watch_var" not in build or "Watch Live" not in build:
    failures.append("watch after batch: Quick Add has no Watch option")  # noqa: F821
add = inspect.getsource(QueueTab._on_add_features)
if '"action_type": "watch"' not in add:
    failures.append("watch after batch: choosing Watch queues no watch item")  # noqa: F821
if "watch_minutes" not in add:
    failures.append("watch after batch: the watch has no duration, so it can "  # noqa: F821
                    "neither be bounded nor left running until Stop")
ready = inspect.getsource(QueueTab._update_features_btn)
if "_feat_watch_var" not in ready:
    failures.append("watch after batch: Watch alone does not enable the Add "  # noqa: F821
                    "button")

# The batch starts it at the end, with the watchers, and never processes it
# as an ordinary item.
m = DriverManager()
logs = []
m.log = logs.append
m._fast_tests = True
started = {}


async def _fake_watch(url, minutes=None, profile_names=None):
    started["url"] = url
    started["minutes"] = minutes
    started["profiles"] = list(profile_names or [])

m._do_watch = _fake_watch
items = [{"action_type": "watch", "profile_name": p, "post_url": URL,
          "watch_minutes": 5} for p in PROFILES]
asyncio.run(m._do_batch(items))

if started.get("url") != URL:
    failures.append(f"watch after batch: the watch never started: {started}")  # noqa: F821
if started.get("profiles") != PROFILES:
    failures.append(f"watch after batch: wrong watchers: {started.get('profiles')}")  # noqa: F821
if started.get("minutes") != 5:
    failures.append(f"watch after batch: the duration was lost: "  # noqa: F821
                    f"{started.get('minutes')}")
if any("Starting batch: 2 item" in line for line in logs):
    failures.append("watch after batch: watch items were counted as batch work, "  # noqa: F821
                    "so the run reports actions it never performed")

print("FAILED" if [f for f in failures if "watch after batch" in f] else "ok")  # noqa: F821
