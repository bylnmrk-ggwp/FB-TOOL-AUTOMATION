"""The visible watch lays its windows out ten to a row.

The squarest-grid-that-fits changed shape with the number of pages: 9 open
made 3x3, 46 made 7x7, so the wall never looked the same twice. A fixed column
count is what makes it one shape, and ten is the one asked for - a wave of 30
is 10 across and 3 down.

Ten columns is narrower per tile than five, so width is what runs out first.
Ten cells plus their gutters must fit the desktop and still clear Chromium's
~515-unit minimum window width, or every window comes back clamped and the
wall piles up instead of tiling. The scale factor is what buys units, so it
has to follow the page count rather than sit at one constant, and the tiler
must convert the desktop with the same factor the browser launched with or the
two disagree by construction.
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

# 30 pages is the wave the operator watches: ten across, three down.
rows_for_30 = math.ceil(30 / DriverManager.WATCH_GRID_COLS)
if (DriverManager.WATCH_GRID_COLS, rows_for_30) != (10, 3):
    failures.append(f"watch grid: 30 pages lay out "  # noqa: F821
                    f"{DriverManager.WATCH_GRID_COLS}x{rows_for_30}, not 10x3")

scale = DriverManager.WATCH_GRID_SCALE
if not (0 < scale < 1):
    failures.append(f"watch grid: WATCH_GRID_SCALE {scale!r} does not shrink the "  # noqa: F821
                    f"browser unit")

# The launch factor follows the page count, and the tiler reads the one the
# browser was launched with - not the constant, or a 5x6 grid on a small
# screen is laid out in units the browser never agreed to.
if "_grid_scale_for(len(active))" not in watch:
    failures.append("watch grid: the launch scale ignores how many pages will "  # noqa: F821
                    "open, so six rows on a small desktop come back clamped")
if "_watch_scale" not in tile:
    failures.append("watch grid: the tiler converts the desktop with the class "  # noqa: F821
                    "constant instead of the factor the browser launched with")


def _tile_side(w: int, h: int, count: int, scale: float) -> float:
    """One tile's side in browser units, the same arithmetic the tiler uses."""
    cols = DriverManager.WATCH_GRID_COLS
    rows = max(1, math.ceil(count / cols))
    gap = DriverManager.WATCH_GRID_GAP
    return min((w / scale - gap * (cols + 1)) // cols,
               (h / scale - gap * (rows + 1)) // rows)


# Every desktop the fleet runs on must produce a tile Chromium will honour, at
# the wave sizes it actually opens. 1366x768 is the case that fails at a fixed
# scale, which is why the scale is computed.
_real_desktop = DriverManager._desktop_size
_probe = DriverManager()
try:
    for w, h in ((1920, 1080), (1536, 864), (1366, 768), (1280, 720)):
        DriverManager._desktop_size = staticmethod(lambda w=w, h=h: (w, h))
        for count in (8, 30, 50):
            chosen = _probe._grid_scale_for(count)
            side = _tile_side(w, h, count, chosen)
            if side < DriverManager.WATCH_GRID_MIN_TILE:
                failures.append(  # noqa: F821
                    f"watch grid: {count} pages on a {w}x{h} desktop tile at "
                    f"{side:.0f} units (scale {chosen}), under Chromium's "
                    f"minimum - the windows would be clamped into a pile")
finally:
    DriverManager._desktop_size = _real_desktop

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

# The grid is measured from the desktop, not from what the page claims its
# screen is: a watch context reported 1280x800 while devicePixelRatio was
# 0.25, which squeezed the whole grid into a corner of the real screen.
if "_desktop_size" not in tile:
    failures.append("watch grid: the layout still trusts the page's own screen "  # noqa: F821
                    "size, which a watch context reports wrongly")
size = DriverManager._desktop_size()
if size is None or not (size[0] > 200 and size[1] > 200):
    failures.append(f"watch grid: the desktop size came back as {size!r}")  # noqa: F821

print("FAILED" if [f for f in failures if "watch grid" in f] else "ok")  # noqa: F821
