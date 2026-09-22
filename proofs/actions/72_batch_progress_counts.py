"""Batch progress separates what was attempted from what worked.

The line read "53/53 done..." while the final tally said "49/53 successful",
so a run that reacted with 49 accounts looked like 53 had acted. Same number
of items, two different facts, one of them stated as if it were the other.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("batch progress counts")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

src = inspect.getsource(DriverManager._do_batch)

if "done..." in src:
    failures.append("batch progress counts: progress still says \"N/N done\", which "  # noqa: F821
                    "reads as N accounts having acted")
if "attempted" not in src:
    failures.append("batch progress counts: progress does not say the number is "  # noqa: F821
                    "attempts")
if '"succeeded"' not in src:
    failures.append("batch progress counts: the progress event carries no success "  # noqa: F821
                    "count, so a UI cannot show one")
# The count shown must be the same one the final tally uses, or the two lines
# can disagree again.
if "{success_count} ok" not in src:
    failures.append("batch progress counts: progress does not report success_count, "  # noqa: F821
                    "the tally the final line uses")
if "Batch complete: {success_count}/{total} successful" not in src:
    failures.append("batch progress counts: the final tally no longer reports "  # noqa: F821
                    "success_count")

print("FAILED" if [f for f in failures if "batch progress counts" in f] else "ok")  # noqa: F821
