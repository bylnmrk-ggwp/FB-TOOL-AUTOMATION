"""A running queue can be stopped without killing the app.

Once a run started there was no way out of it: Start Queue went disabled and
the worker walked every batch to the end. The stop is a flag, not a queued
command - the worker handles one command at a time, so a message sent while
_do_batch is running would not be read until the run it was meant to end had
already finished.

The item in flight finishes. Killing a half-posted comment would leave
Facebook in a state nothing here can observe, so the stop takes effect at the
next item and the next batch.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("stop queue")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402
from src.ui.queue_tab import QueueTab  # noqa: E402

# The control exists and does not go through the command queue.
if not hasattr(DriverManager, "stop_queue"):
    failures.append("stop queue: the driver has no stop_queue, so a run cannot be "  # noqa: F821
                    "ended once it starts")
else:
    stop = inspect.getsource(DriverManager.stop_queue)
    if "cmd_queue" in stop:
        failures.append("stop queue: the stop is queued as a command, which a "  # noqa: F821
                        "running batch will not read until it has finished")
    if "_stop_batch" not in stop:
        failures.append("stop queue: the stop sets nothing the batch can see")  # noqa: F821

batch = inspect.getsource(DriverManager._do_batch)
if batch.count("_stop_batch.is_set()") < 2:
    failures.append("stop queue: the batch checks for a stop fewer than twice, so "  # noqa: F821
                    "a long run would keep going between items or between batches")
if "_stop_batch.clear()" not in batch:
    failures.append("stop queue: the flag is never cleared, so one press would "  # noqa: F821
                    "kill every later run too")

# A stopped run must not then hand the fleet over to a watch.
if "watch_items and self._stop_batch.is_set()" not in batch:
    failures.append("stop queue: a stopped run still starts the watch, so profiles "  # noqa: F821
                    "stay on the post after the operator said stop")

# Real flag behaviour, not just its text.
m = DriverManager()
if m._stop_batch.is_set():
    failures.append("stop queue: a fresh manager starts out stopped")  # noqa: F821
m.stop_queue()
if not m._stop_batch.is_set():
    failures.append("stop queue: stop_queue() does not raise the flag")  # noqa: F821

# The desktop tab offers it, only while a run is on.
build = inspect.getsource(QueueTab._build_ui)
if "stop_btn" not in build or "Stop Queue" not in build:
    failures.append("stop queue: the queue tab has no Stop Queue button")  # noqa: F821
running = inspect.getsource(QueueTab.set_running)
if "stop_btn" not in running:
    failures.append("stop queue: the Stop button's state does not follow the run, "  # noqa: F821
                    "so it is pressable with nothing running")
handler = inspect.getsource(QueueTab._on_stop_queue)
if "_on_stop_queue_cb" not in handler:
    failures.append("stop queue: pressing Stop calls nothing")  # noqa: F821

print("FAILED" if [f for f in failures if "stop queue" in f] else "ok")  # noqa: F821
