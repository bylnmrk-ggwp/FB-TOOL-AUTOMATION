"""SheetWriter degrades to an inert object when there is no service-account
key: .on is False, .error says why, and every write reports False instead of
raising. Nothing here touches the network - the missing key short-circuits
construction before the first HTTP call.
"""
import sys

sys.path.insert(0, str(ROOT))

step("sheet_status.SheetWriter")
from src.storage import sheet_status as _ss

for _name in ("write", "mark_in_progress"):
    if not callable(getattr(getattr(_ss, "SheetWriter", None), _name, None)):
        failures.append(f"SheetWriter.{_name} missing")

_missing = ROOT / "does-not-exist.json"
_w = _ss.SheetWriter(key_path=_missing)
if _w.on is not False:
    failures.append(f"SheetWriter.on with no key: {_w.on!r} (expected False)")
if not isinstance(_w.error, str) or not _w.error:
    failures.append(f"SheetWriter.error with no key: {_w.error!r} (expected text)")
elif "key" not in _w.error.lower() or _missing.name not in _w.error:
    failures.append(f"SheetWriter.error does not name the missing key: {_w.error!r}")
if _w.write("x", "y") is not False:
    failures.append("SheetWriter.write must return False when off")
if _w.mark_in_progress("x") is not False:
    failures.append("SheetWriter.mark_in_progress must return False when off")
print("ok" if not [f for f in failures if "SheetWriter" in f] else "FAILED")
