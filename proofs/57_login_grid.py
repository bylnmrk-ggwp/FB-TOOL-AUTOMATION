"""A visible login wave tiles its windows instead of stacking them.

Five logins at once used to mean five windows on top of each other, so the
operator could watch exactly one of them. grid_slot() hands each worker its
own rectangle, sized so the whole wave fits the screen at once - small, but
all of them visible.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("login window grid")  # noqa: F821

from src.core.browser_choice import grid_slot  # noqa: E402

SCREEN = (1536, 864)

for count in (1, 2, 4, 5, 9, 25):
    rects = [grid_slot(i, count, *SCREEN) for i in range(count)]
    if any(w <= 0 or h <= 0 for _, _, w, h in rects):
        failures.append(f"login grid: count {count} produced a zero-sized window: {rects}")  # noqa: F821
    # Every window has to be on screen.
    for x, y, w, h in rects:
        if x < 0 or y < 0 or x + w > SCREEN[0] or y + h > SCREEN[1]:
            failures.append(f"login grid: count {count} put a window off screen: {(x, y, w, h)}")  # noqa: F821
            break
    # No two workers may share a slot, or windows stack again.
    if len({(x, y) for x, y, _, _ in rects}) != count:
        failures.append(f"login grid: count {count} gave overlapping positions: {rects}")  # noqa: F821

# A wave of five must not be laid out as five columns of slivers: each window
# should keep a usable width.
five = [grid_slot(i, 5, *SCREEN) for i in range(5)]
if any(w < 300 for _, _, w, _ in five):
    failures.append(f"login grid: five windows are too narrow to read: "  # noqa: F821
                    f"{[w for _, _, w, _ in five]}")

# The real wave width has to tile the screen as a full 5x5 - that is the
# layout the operator asked for, and it is what makes 25 windows watchable.
from src.core.driver_manager import DriverManager  # noqa: E402
wave = int(DriverManager.LOGIN_PARALLEL)
rects = [grid_slot(i, wave, *SCREEN) for i in range(wave)]
cols = len({x for x, _, _, _ in rects})
rows = len({y for _, y, _, _ in rects})
if (cols, rows) != (5, 5):
    failures.append(f"login grid: a wave of {wave} tiles as {cols}x{rows}, not 5x5")  # noqa: F821

# Out-of-range indexes must not explode; they wrap into the grid.
try:
    grid_slot(99, 5, *SCREEN)
except Exception as e:  # noqa: BLE001
    failures.append(f"login grid: an index past the wave raised {type(e).__name__}")  # noqa: F821

print("FAILED" if [f for f in failures if "login grid" in f] else "ok")  # noqa: F821
