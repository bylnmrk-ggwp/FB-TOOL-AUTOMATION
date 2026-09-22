"""One SQLite connection per thread, and no N+1 restriction lookup.

The web server put four threads on the database at once - the FastAPI
threadpool, the EventBridge, the DriverManager worker and the sheet watcher -
against a single module-global connection. That is what
`sqlite3.InterfaceError: bad parameter or other API misuse` was: two threads
inside conn.execute() at the same moment. GET /api/accounts made it certain
by calling share_restriction() once per roster row, 261 times a refresh.
"""
import sys
import threading

sys.path.insert(0, str(ROOT))  # noqa: F821  - verify.py injects ROOT

step("db connection is per-thread")  # noqa: F821

from src.server import data  # noqa: E402
from src.storage import database as db  # noqa: E402

# Every thread must get its own connection object, or concurrent execute()
# on the shared one raises InterfaceError under load.
seen = {}
barrier = threading.Barrier(4)


def grab(i):
    barrier.wait()
    seen[i] = id(db._get_conn())


threads = [threading.Thread(target=grab, args=(i,)) for i in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()

if len(set(seen.values())) != len(seen):
    failures.append(  # noqa: F821
        f"_get_conn() handed the same connection to different threads: {seen}")
if id(db._get_conn()) in set(seen.values()):
    failures.append("_get_conn() reused a worker thread's connection on the main thread")

# Hammer the real read path from several threads: this is the call that was
# raising in production (accounts_rows -> share_restriction per row).
errors = []


def hammer():
    try:
        for _ in range(8):
            db.list_accounts()
            db.share_restriction("verify-no-such-profile")
            data.accounts_rows()
    except Exception as e:  # noqa: BLE001 - any raise here is the defect
        errors.append(f"{type(e).__name__}: {e}")


workers = [threading.Thread(target=hammer) for _ in range(4)]
for t in workers:
    t.start()
for t in workers:
    t.join()
if errors:
    failures.append(f"concurrent database reads raised: {errors[:3]}")  # noqa: F821

# The N+1 is gone: one query answers every row.
if not hasattr(data, "restricted_profiles"):
    failures.append("data.restricted_profiles() missing - accounts_rows still queries per row")
else:
    got = data.restricted_profiles()
    if not isinstance(got, set):
        failures.append(f"restricted_profiles() must return a set, got {type(got).__name__}")

_src = open(ROOT / "src" / "server" / "data.py", encoding="utf-8").read()  # noqa: F821
if "_restricted(" in _src:
    failures.append("data.py still calls the per-row _restricted() helper")  # noqa: F821

print("FAILED" if [f for f in failures if "connection" in f or "concurrent" in f  # noqa: F821
                   or "restricted" in f or "_restricted" in f] else "ok")
