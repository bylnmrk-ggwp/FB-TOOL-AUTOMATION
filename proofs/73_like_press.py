"""Like is pressed with a pointer, not with locator.click().

Facebook nests the real Like control and its <i> icon inside the React
button. Playwright's actionability check then refuses the click - "<i ...>
from <div aria-label='Like'> subtree intercepts pointer events" - retries for
five seconds and raises. On one post that killed every reaction in the run
while comments on the same post went through.

A mouse press at a point inside the element lands on whatever is on top,
which is exactly what a person clicking there hits.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("like press")  # noqa: F821

from src.core import human_input as human  # noqa: E402
from src.core.facebook_automation import FacebookAutomation  # noqa: E402

src = inspect.getsource(FacebookAutomation._auto_react)
like_block = src.split('if reaction == "like":', 1)[-1].split("label = self.REACTION_LABELS")[0]

if "human_input.click" not in like_block:
    failures.append("like press: Like is still pressed with locator.click(), which "  # noqa: F821
                    "an intercepting child element makes time out")
if "await like_locator.click(timeout=5000)\n" in like_block:
    failures.append("like press: a bare locator.click() with no force fallback is "  # noqa: F821
                    "still the first attempt")
if "force=True" not in like_block:
    failures.append("like press: no forced click remains as a fallback")  # noqa: F821

# The pointer press must not consult actionability: it goes through
# page.mouse, which is what makes it immune to an intercepting child.
press = inspect.getsource(human.click)
if "page.mouse.down" not in press or "page.mouse.up" not in press:
    failures.append("like press: human_input.click no longer issues a real mouse "  # noqa: F821
                    "press, so interception would block it again")


class _Mouse:
    def __init__(self):
        self.events = []

    async def move(self, x, y):
        self.events.append(("move", round(x), round(y)))

    async def down(self):
        self.events.append(("down",))

    async def up(self):
        self.events.append(("up",))


class _Page:
    def __init__(self):
        self.mouse = _Mouse()


class _Intercepted:
    """An element whose own click always fails, as Playwright's does when a
    child intercepts the pointer."""

    async def scroll_into_view_if_needed(self):
        return None

    async def bounding_box(self):
        return {"x": 200.0, "y": 300.0, "width": 90.0, "height": 36.0}

    async def click(self, **kw):
        raise AssertionError("locator.click() would time out on this element")


page = _Page()
if not asyncio.run(human.click(page, _Intercepted(), settle=False)):
    failures.append("like press: the pointer press gave up on an element whose own "  # noqa: F821
                    "click is blocked")
if ("down",) not in page.mouse.events or ("up",) not in page.mouse.events:
    failures.append(f"like press: no button press was issued: {page.mouse.events}")  # noqa: F821
last_move = [e for e in page.mouse.events if e[0] == "move"][-1]
if not (200 <= last_move[1] <= 290 and 300 <= last_move[2] <= 336):
    failures.append(f"like press: the pointer did not land inside the button: "  # noqa: F821
                    f"{last_move}")

print("FAILED" if [f for f in failures if "like press" in f] else "ok")  # noqa: F821
