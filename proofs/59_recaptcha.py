"""An "I'm not a robot" box is ticked, and a picture challenge goes to a human.

A login that hits reCAPTCHA and ignores it sits on the login page, and the
run wrote the account off as a wrong password. The checkbox is clicked here,
which is all a profile with history usually needs. A picture challenge is
meant for a person: the window is enlarged and raised so the operator can
answer it, and headless - where nobody can - the run takes the verdict at
once instead of hanging.
"""
import asyncio
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("recaptcha")  # noqa: F821

from src.core.driver_manager import login_reason  # noqa: E402
from src.core.facebook_automation import FacebookAutomation  # noqa: E402

ANCHOR = "https://www.google.com/recaptcha/api2/anchor?k=x"
BFRAME = "https://www.google.com/recaptcha/api2/bframe?k=x"


class _Locator:
    def __init__(self, frame):
        self._frame = frame

    async def click(self, timeout=None):
        self._frame.clicked = True
        if self._frame.solves_on_click:
            self._frame.page.token = True


class _Frame:
    def __init__(self, url, page, solves_on_click=False):
        self.url = url
        self.page = page
        self.clicked = False
        self.solves_on_click = solves_on_click

    def locator(self, selector):
        return _Locator(self)


class _Page:
    """Enough of a Playwright page for the captcha path: frames, the token
    textarea, and the screen size the tiling uses."""

    def __init__(self, frames=(), token=False):
        self.token = token
        self.frames = [_Frame(u, self, s) for u, s in frames]
        self.raised = False

    async def evaluate(self, script):
        if "availWidth" in script:
            return [3840, 2160]
        return 1 if self.token else 0

    async def bring_to_front(self):
        self.raised = True


def _auto(page, tile=(0, 25)):
    auto = FacebookAutomation(log_callback=lambda m: None)
    auto.page = page
    auto._tile = tile
    auto._set_window_bounds = lambda bounds: asyncio.sleep(0)
    auto._tile_window = lambda slot, count: asyncio.sleep(0)
    return auto


# No reCAPTCHA on the page: the login path must not wait for one.
auto = _auto(_Page())
if asyncio.run(auto.handle_recaptcha()) != "none":
    failures.append("recaptcha: a page without a checkbox should report 'none'")  # noqa: F821

# The checkbox alone issues a token - the usual case on a profile with history.
page = _Page(frames=[(ANCHOR, True)])
auto = _auto(page)
if asyncio.run(auto.handle_recaptcha()) != "solved":
    failures.append("recaptcha: ticking the box did not count as solved")  # noqa: F821
if not page.frames[0].clicked:
    failures.append("recaptcha: the checkbox was never clicked")  # noqa: F821

# A picture challenge headless (no visible window) is not waited out: nobody
# is there to answer it, and the wave must move on.
page = _Page(frames=[(ANCHOR, False), (BFRAME, False)])
auto = _auto(page, tile=None)
if asyncio.run(auto.handle_recaptcha()) != "needs human":
    failures.append("recaptcha: a headless picture challenge must not be waited out")  # noqa: F821
if page.raised:
    failures.append("recaptcha: a headless run raised a window nobody can see")  # noqa: F821

# Visible, and the operator answers it: the window is raised for them first.
page = _Page(frames=[(ANCHOR, False), (BFRAME, False)])
auto = _auto(page)


async def _answer():
    task = asyncio.ensure_future(auto.handle_recaptcha(wait_s=5))
    await asyncio.sleep(1.2)
    page.token = True          # the person ticks the pictures
    return await task

if asyncio.run(_answer()) != "solved":
    failures.append("recaptcha: an answered challenge should report 'solved'")  # noqa: F821
if not page.raised:
    failures.append("recaptcha: the window was never raised for the operator, so "  # noqa: F821
                    "the challenge sits in a cell too small to answer")

# Facebook's own challenge is a different widget on a different host, with no
# checkbox at all. It was invisible to a detector that only knew Google's.
ARKOSE = "https://client-api.arkoselabs.com/fc/assets/ec-game-core/"
page = _Page(frames=[(ARKOSE, False)])
auto = _auto(page, tile=None)
if asyncio.run(auto.handle_recaptcha()) != "needs human":
    failures.append("recaptcha: Facebook's own picture challenge is not detected, so "  # noqa: F821
                    "it is recorded as something else")

page = _Page(frames=[(ARKOSE, False)])
auto = _auto(page)


async def _answer_arkose():
    task = asyncio.ensure_future(auto.handle_recaptcha(wait_s=5))
    await asyncio.sleep(1.2)
    page.frames = []           # the person finishes the puzzle
    return await task

if asyncio.run(_answer_arkose()) != "solved":
    failures.append("recaptcha: an answered Facebook challenge is not noticed")  # noqa: F821
if not page.raised:
    failures.append("recaptcha: the window was not raised for the Facebook challenge")  # noqa: F821

# The sheet reason says captcha, not "wrong password".
if login_reason("captcha - solve it in the window") != "captcha":
    failures.append("recaptcha: the recorded reason does not say captcha")  # noqa: F821

print("FAILED" if [f for f in failures if "recaptcha" in f] else "ok")  # noqa: F821
