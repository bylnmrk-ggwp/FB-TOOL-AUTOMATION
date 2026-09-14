"""The visible watch lays its windows out ten to a row.

The squarest-grid-that-fits changed shape with the number of pages: 9 open
made 3x3, 46 made 7x7, so the wall never looked the same twice. Ten to a row
is fixed, with as many rows as the pages need - and a tenth of a screen is
far below Chromium's minimum window width, so the watch browser has to shrink
its own unit the way the login grid does or every window comes back clamped.
"""
import inspect
import math
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("watch grid")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

if DriverManager.WATCH_GRID_COLS != 10:
    failures.append(f"watch grid: {DriverManager.WATCH_GRID_COLS} windows to a row, "  # noqa: F821
                    f"not the ten that was asked for")

tile = inspect.getsource(DriverManager._tile_watch_windows)
if "math.sqrt" in tile:
    failures.append("watch grid: the grid still resizes itself to the number of "  # noqa: F821
                    "pages, so the wall changes shape every run")
if "WATCH_GRID_COLS" not in tile:
    failures.append("watch grid: the tiling does not use the fixed grid")  # noqa: F821
if "math.ceil(count / cols)" not in tile:
    failures.append("watch grid: the number of rows does not follow the page "  # noqa: F821
                    "count, so windows would fall off the bottom or waste the screen")

watch = inspect.getsource(DriverManager._do_watch)
if "force-device-scale-factor" not in watch:
    failures.append("watch grid: the watch browser keeps its normal unit, so "  # noqa: F821
                    "Chromium clamps every cell and the windows overlap")
if 'mode == "visible"' not in watch:
    failures.append("watch grid: the scale factor is applied even to hidden runs, "  # noqa: F821
                    "which have no windows to place")

# The cell has to clear Chromium's ~515-unit minimum in the browser's own
# space. At scale s that space is the screen divided by s.
scale = DriverManager.WATCH_GRID_SCALE
if not (0 < scale < 1):
    failures.append(f"watch grid: WATCH_GRID_SCALE {scale!r} does not shrink the "  # noqa: F821
                    f"browser unit")
else:
    space_w = 1920 / scale
    cell_w = space_w / DriverManager.WATCH_GRID_COLS
    if cell_w < 520:
        failures.append(f"watch grid: a cell is {cell_w:.0f} units wide, under "  # noqa: F821
                        f"Chromium's minimum - the windows would be clamped")

print("FAILED" if [f for f in failures if "watch grid" in f] else "ok")  # noqa: F821
