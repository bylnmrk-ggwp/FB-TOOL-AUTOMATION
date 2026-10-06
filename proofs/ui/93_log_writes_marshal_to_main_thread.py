"""Log writes from the worker thread never touch Tk directly.

The DriverManager runs on a background thread and logs from there - the whole
watch heartbeat does. write() wrote straight into the Tk Text widget, which is
a cross-thread Tk call: it survived while the main loop ran, then crashed at
shutdown, when manager.stop() drives _do_quit -> _stop_watch -> self.log after
mainloop() has returned:

    RuntimeError: main thread is not in main loop
      log_tab.py write -> self.text.config(state="normal")

and the error handler logged again, double-faulting.

So write() only records: the file (already thread-safe) and a queue. The Tk
Text is touched only by _drain_log, which runs on the main thread. A worker
write enqueues and returns; nothing it does can reach Tk.
"""
import sys
import threading
import tempfile
from pathlib import Path
import tkinter as tk

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("log marshal to main thread")  # noqa: F821

from src.ui.log_tab import LogTab  # noqa: E402

MARK = "from-worker-xyz-93"

root = tk.Tk()
root.withdraw()
try:
    log = LogTab(root)
    log.LOG_DIR = Path(tempfile.mkdtemp())   # don't touch the real app log

    # 1. A write from a WORKER thread must not touch Tk - no RuntimeError,
    #    no hang on the Tcl interpreter owned by the main thread.
    err = []

    def worker():
        try:
            log.write(MARK)
        except Exception as e:  # noqa: BLE001
            err.append(f"{type(e).__name__}: {e}")

    t = threading.Thread(target=worker)
    t.start()
    t.join(5)
    if t.is_alive():
        failures.append(  # noqa: F821
            "log marshal: a worker-thread write hung - it blocked on a Tk "
            "call owned by the main thread")
    if err:
        failures.append(  # noqa: F821
            f"log marshal: a worker-thread write raised {err[0]} - write() "
            f"touched Tk off the main thread")

    # 2. The worker did not render into the widget itself; rendering is
    #    deferred to the main-thread drain.
    if MARK in log.text.get("1.0", "end"):
        failures.append(  # noqa: F821
            "log marshal: the worker wrote straight into the Tk widget "
            "instead of queueing for the main thread")

    # 3. The main-thread drain renders the queued line.
    log._drain_log()
    if MARK not in log.text.get("1.0", "end"):
        failures.append(  # noqa: F821
            "log marshal: the queued message never rendered on the "
            "main-thread drain")

    # 4. It reached the file regardless - the record that survives a session.
    p = log.log_path
    log.close_log_file()
    on_disk = p.read_text(encoding="utf-8") if p.exists() else ""
    if MARK not in on_disk:
        failures.append(  # noqa: F821
            "log marshal: the message never reached the log file")
finally:
    try:
        root.destroy()
    except Exception:
        pass

print("FAILED" if [f for f in failures  # noqa: F821
                   if "log marshal" in f] else "ok")
