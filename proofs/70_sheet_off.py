"""With the sheet off, nothing reaches for Google.

The roster, the credentials and every verdict live in the local database;
the accounts themselves live in the browser profiles on this PC. Neither
needs a round trip to Google, and a PC without DNS was spending one per
account to be told it has no network.

Off means off at the source - no token, no credentials, no socket - not a
call that fails politely.
"""
import socket
import sys
import time

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("sheet off")  # noqa: F821

from src.storage import sheet_status as ss  # noqa: E402
from src.storage.roster_sheet import SheetWatcher  # noqa: E402

if ss.SHEET_SYNC:
    failures.append("sheet off: the sheet mirror is still on by default")  # noqa: F821
if ss.sheet_enabled():
    failures.append("sheet off: sheet_enabled() is true with the mirror off")  # noqa: F821

# No socket may be opened while the sheet is off.
opened = []
_real_connection = socket.create_connection
_real_socket = socket.socket


class _NoSocket(_real_socket):
    def connect(self, address):
        opened.append(address)
        raise AssertionError(f"the sheet is off but something dialled {address}")


def _no_connection(address, *a, **kw):
    opened.append(address)
    raise AssertionError(f"the sheet is off but something dialled {address}")


socket.create_connection = _no_connection
socket.socket = _NoSocket
try:
    started = time.monotonic()
    if ss.push_account_status("someone@example.com") != "":
        failures.append("sheet off: a status push wrote something")  # noqa: F821
    writer = ss.SheetWriter()
    if writer.on or "off" not in writer.error.lower():
        failures.append(f"sheet off: the writer is not off: {writer.error!r}")  # noqa: F821
    if writer.write("someone@example.com", "LOGGED IN"):
        failures.append("sheet off: an off writer reported a successful write")  # noqa: F821

    watcher = SheetWatcher(interval=0.1)
    watcher.start()
    watcher.join(timeout=3)
    if watcher.is_alive():
        failures.append("sheet off: the roster watcher is still polling")  # noqa: F821
        watcher.stop()
    if time.monotonic() - started > 5:
        failures.append("sheet off: the off path is slow, so it is doing work")  # noqa: F821
finally:
    socket.create_connection = _real_connection
    socket.socket = _real_socket

if opened:
    failures.append(f"sheet off: {len(opened)} network connection(s) attempted: "  # noqa: F821
                    f"{opened[:2]}")

# Turning it back on is one flag - nothing here is deleted.
ss.SHEET_SYNC = True
try:
    if not ss.sheet_enabled():
        failures.append("sheet off: the mirror cannot be switched back on")  # noqa: F821
finally:
    ss.SHEET_SYNC = False

print("FAILED" if [f for f in failures if "sheet off" in f] else "ok")  # noqa: F821
