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

# Square tiles with a gutter, centred - the layout in the icon, not a screen
# chopped into whatever rectangles fit.
if "cell_w = cell_h" not in tile:
    failures.append("watch grid: the tiles are not square")  # noqa: F821
if "WATCH_GRID_GAP" not in tile:
    failures.append("watch grid: there is no gap between windows, so the wall "  # noqa: F821
                    "reads as one sheet instead of a grid")
if "pad_x" not in tile or "pad_y" not in tile:
    failures.append("watch grid: the block is not centred, so a half-full last "  # noqa: F821
                    "row sits in a corner")
if "max(gap, int((sw" not in tile or "max(gap, int((sh" not in tile:
    failures.append("watch grid: there is no margin at the screen edges, so the "  # noqa: F821
                    "outer windows sit flush against them")

# Tiles are laid left to right, filling a row before starting the next.
if "(i % cols)" not in tile or "(i // cols)" not in tile:
    failures.append("watch grid: the fill order is not left to right by row")  # noqa: F821
if not (0 < DriverManager.WATCH_GRID_GAP <= 200):
    failures.append(f"watch grid: the gutter is {DriverManager.WATCH_GRID_GAP}, "  # noqa: F821
                    f"which is not a usable gap")

# The arithmetic has to leave a real tile at fleet size.
space_w, space_h = 1920 / DriverManager.WATCH_GRID_SCALE, 1080 / DriverManager.WATCH_GRID_SCALE
cols = DriverManager.WATCH_GRID_COLS
rows = 5
gap = DriverManager.WATCH_GRID_GAP
side = min((space_w - gap * (cols + 1)) // cols, (space_h - gap * (rows + 1)) // rows)
if side < 520:
    failures.append(f"watch grid: a tile is {side:.0f} units, under Chromium's "  # noqa: F821
                    f"minimum window width - the windows would be clamped")

print("FAILED" if [f for f in failures if "watch grid" in f] else "ok")  # noqa: F821
