"""Input looks like a hand, not like a script.

locator.fill() assigns a whole value in one DOM write and locator.click()
teleports the pointer to an element's exact centre. Those two facts are what
an anti-bot score reads, and the score is what puts an "I'm not a robot" box
on the login form. Every field is typed key by key with uneven spacing, and
every press is a real pointer that travelled there.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("human input")  # noqa: F821

from src.core import human_input as human  # noqa: E402
from src.core.facebook_automation import LOGIN_FLAGS, FacebookAutomation  # noqa: E402

BOX = {"x": 100.0, "y": 200.0, "width": 300.0, "height": 40.0}


class _Mouse:
    def __init__(self, page):
        self.page = page

    async def move(self, x, y):
        self.page.moves.append((x, y))

    async def down(self):
        self.page.events.append("down")

    async def up(self):
        self.page.events.append("up")

    async def wheel(self, dx, dy):
        self.page.events.append(("wheel", dx, dy))


class _Keyboard:
    def __init__(self, page):
        self.page = page

    async def type(self, text):
        self.page.typed.append(text)

    async def press(self, key):
        self.page.events.append(("press", key))


class _Page:
    def __init__(self):
        self.moves = []
        self.typed = []
        self.events = []
        self.mouse = _Mouse(self)
        self.keyboard = _Keyboard(self)


class _Locator:
    def __init__(self, box=BOX):
        self._box = box
        self.filled = []

    async def scroll_into_view_if_needed(self):
        return None

    async def bounding_box(self):
        return self._box

    async def fill(self, value):
        self.filled.append(value)

    async def click(self, **kw):
        self.filled.append("CLICKED")


# ── Typing ────────────────────────────────────────────
page, field = _Page(), _Locator()
delays = []
_real_sleep = asyncio.sleep


async def _timed_sleep(seconds, *a, **kw):
    delays.append(seconds)
    return await _real_sleep(0, *a, **kw)


human.asyncio.sleep = _timed_sleep
try:
    # click_first=False so the measured gaps are keystrokes, not the pointer
    # travel that precedes them; the click path has its own check below.
    asyncio.run(human.type_text(page, field, "abc@example.com", click_first=False))
finally:
    human.asyncio.sleep = _real_sleep

if "".join(page.typed) != "abc@example.com":
    failures.append(f"human input: the field did not receive the text: {page.typed}")  # noqa: F821
if len(page.typed) != len("abc@example.com"):
    failures.append("human input: the value was assigned at once instead of typed "  # noqa: F821
                    "key by key")
key_delays = [d for d in delays if d > 0]
if len(set(key_delays)) < len(key_delays) * 0.8:
    failures.append("human input: keystrokes share one delay, which is a machine "  # noqa: F821
                    "signature")
if key_delays and min(key_delays) < 0.02:
    failures.append(f"human input: a keystroke gap of {min(key_delays):.3f}s is faster "  # noqa: F821
                    f"than a person can type")

# ── Clicking ──────────────────────────────────────────
page = _Page()
if not asyncio.run(human.click(page, _Locator(), settle=False)):
    failures.append("human input: click reported it could not press the element")  # noqa: F821
if len(page.moves) < 5:
    failures.append(f"human input: the pointer jumped to the target in "  # noqa: F821
                    f"{len(page.moves)} move(s) instead of travelling")
if page.events[:2] != ["down", "up"]:
    failures.append(f"human input: the press was not a real button down/up: "  # noqa: F821
                    f"{page.events}")
last = page.moves[-1]
if not (BOX["x"] <= last[0] <= BOX["x"] + BOX["width"]
        and BOX["y"] <= last[1] <= BOX["y"] + BOX["height"]):
    failures.append(f"human input: the click landed outside the element: {last}")  # noqa: F821

# The same element must not be hit on the same pixel every time.
spots = set()
for _ in range(12):
    p = _Page()
    asyncio.run(human.click(p, _Locator(), settle=False))
    spots.add((round(p.moves[-1][0], 1), round(p.moves[-1][1], 1)))
if len(spots) < 8:
    failures.append(f"human input: 12 clicks landed on {len(spots)} distinct points - "  # noqa: F821
                    f"a fixed hit point is its own signature")
centre = (BOX["x"] + BOX["width"] / 2, BOX["y"] + BOX["height"] / 2)
if any(abs(sx - centre[0]) < 0.01 and abs(sy - centre[1]) < 0.01 for sx, sy in spots):
    failures.append("human input: a click landed on the exact centre of the element")  # noqa: F821

# Travel is a curve, not a straight line: the midpoint must sit off the
# straight path between start and target.
p = _Page()
p._human_pos = (0.0, 0.0)
asyncio.run(human.click(p, _Locator(), settle=False))
x1, y1 = p.moves[-1]
mid = p.moves[len(p.moves) // 2]
straight_y = (mid[0] / x1) * y1 if x1 else mid[1]
if abs(mid[1] - straight_y) < 1.0:
    failures.append("human input: the pointer travelled in a straight line")  # noqa: F821

# ── The login form uses it ────────────────────────────
src = inspect.getsource(FacebookAutomation.login_with_credentials)
if ".fill(email)" in src or ".fill(password)" in src:
    failures.append("human input: the login form still assigns its fields with fill()")  # noqa: F821
if "human_input.type_text" not in src:
    failures.append("human input: the login form does not type its fields")  # noqa: F821
if "human_input.click" not in src:
    failures.append("human input: the Log In button is still pressed without a pointer")  # noqa: F821
# Blink automation and navigator.webdriver used to be answered here, with a
# --disable-blink-features flag in LOGIN_FLAGS and an init script in
# start_browser. Patchright owns both now: it adds that flag to every launch,
# strips the --enable-automation switch no flag of ours could remove, and
# reports navigator.webdriver false natively. So the thing to assert is that
# the automation really is Patchright - a silent fall back to plain
# Playwright would put all three signals back.
import src.core.facebook_automation as _fa  # noqa: E402
if not _fa.async_playwright.__module__.startswith("patchright"):
    failures.append("human input: the browser is driven by "  # noqa: F821
                    f"{_fa.async_playwright.__module__}, not patchright, so it "
                    "advertises Blink automation and navigator.webdriver again")

print("FAILED" if [f for f in failures if "human input" in f] else "ok")  # noqa: F821
