"""Mouse and keyboard input with human timing and human paths.

`locator.fill()` writes a field's value in one DOM assignment and
`locator.click()` teleports the pointer to an element's exact centre. Neither
produces the thing a real person cannot help producing: travel between two
points, a cursor that lands off-centre, keystrokes spaced unevenly, a pause
before pressing a button. Anti-bot scoring reads exactly those signals, and a
poor score is what puts an "I'm not a robot" box in front of a login.

Nothing here defeats a challenge - handle_recaptcha still hands a picture
challenge to a person. This only stops the automation from looking
mechanical while it types a password the operator owns.

All timings are drawn per call, so two logins never share a rhythm.
"""
import asyncio
import math
import random

# One keystroke, in seconds. Ordinary typing sits near the low end; the tail
# is where a person hesitates over a character.
KEY_MIN = 0.055
KEY_MAX = 0.19
# A pause between "words" - after @ . _ - or a space, where the eye moves.
WORD_PAUSE = (0.18, 0.45)
# The rare longer stop, roughly one field in three.
THINK_PAUSE = (0.4, 1.1)
# Mouse travel: more steps over a longer distance, never one jump.
MOVE_STEP_PX = 55
MOVE_STEPS_MIN = 8
MOVE_STEPS_MAX = 28
# How long a real click holds the button down.
CLICK_HOLD = (0.05, 0.14)


def _pos(page) -> tuple[float, float]:
    """Where this page's pointer was left, so the next move starts there
    instead of appearing at the target."""
    return getattr(page, "_human_pos", (random.uniform(60, 400),
                                        random.uniform(60, 400)))


def _remember(page, x: float, y: float) -> None:
    try:
        page._human_pos = (x, y)
    except Exception:
        pass    # a page object that refuses attributes still moves correctly


def _curve(x0: float, y0: float, x1: float, y1: float,
           steps: int) -> list[tuple[float, float]]:
    """Points along a quadratic Bezier from start to target.

    A person's hand arcs and overshoots slightly; a straight line of evenly
    spaced points is as machine-readable as no movement at all. The control
    point is offset perpendicular to the path, and each step carries a pixel
    or two of tremor.
    """
    dx, dy = x1 - x0, y1 - y0
    distance = math.hypot(dx, dy) or 1.0
    # Perpendicular offset, either side, never near zero: a bow that rounds
    # to nothing is a straight line again, which is the shape being avoided.
    bow = random.choice((-1, 1)) * random.uniform(0.07, 0.2) * distance
    cx = (x0 + x1) / 2 - dy / distance * bow
    cy = (y0 + y1) / 2 + dx / distance * bow

    points = []
    for i in range(1, steps + 1):
        t = i / steps
        # Ease in and out: a hand accelerates and then settles.
        t = t * t * (3 - 2 * t)
        u = 1 - t
        x = u * u * x0 + 2 * u * t * cx + t * t * x1
        y = u * u * y0 + 2 * u * t * cy + t * t * y1
        if i < steps:
            x += random.uniform(-1.5, 1.5)
            y += random.uniform(-1.5, 1.5)
        points.append((x, y))
    return points


async def move_to(page, x: float, y: float) -> None:
    """Walk the pointer to (x, y) along a curve, not in one jump."""
    x0, y0 = _pos(page)
    distance = math.hypot(x - x0, y - y0)
    steps = int(min(MOVE_STEPS_MAX,
                    max(MOVE_STEPS_MIN, distance / MOVE_STEP_PX * 8)))
    for px, py in _curve(x0, y0, x, y, steps):
        await page.mouse.move(px, py)
        await asyncio.sleep(random.uniform(0.006, 0.022))
    _remember(page, x, y)


def _target_point(box: dict) -> tuple[float, float]:
    """A point inside an element, off its exact centre.

    Every automated click landing on the same pixel of an element is its own
    signal; a person hits somewhere in the middle third.
    """
    x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
    return x, y


async def click(page, locator, settle: bool = True) -> bool:
    """Move to an element and press it like a person would.

    Returns False when the element has no box to aim at (off screen, or
    detached), so the caller can fall back to locator.click().
    """
    try:
        await locator.scroll_into_view_if_needed()
    except Exception:
        pass
    try:
        box = await locator.bounding_box()
    except Exception:
        box = None
    if not box or not box.get("width") or not box.get("height"):
        return False

    x, y = _target_point(box)
    await move_to(page, x, y)
    if settle:
        # The hand arrives before the click does.
        await asyncio.sleep(random.uniform(0.06, 0.25))
    await page.mouse.down()
    await asyncio.sleep(random.uniform(*CLICK_HOLD))
    await page.mouse.up()
    return True


async def type_text(page, locator, text: str, click_first: bool = True) -> None:
    """Type into a field one key at a time, with human spacing.

    fill() assigns the whole value at once: no keydown timing, no rhythm, and
    on some forms no input events at all. This sends real keystrokes, pausing
    at the boundaries a person pauses at and occasionally stopping to think.
    """
    if click_first and not await click(page, locator):
        try:
            await locator.click()
        except Exception:
            pass
    try:
        await locator.fill("")      # replace whatever a restored form left
    except Exception:
        pass

    thought = False
    for index, ch in enumerate(text):
        await page.keyboard.type(ch)
        delay = random.uniform(KEY_MIN, KEY_MAX)
        if ch in " @._-":
            delay += random.uniform(*WORD_PAUSE)
        elif not thought and index > 2 and random.random() < 0.06:
            delay += random.uniform(*THINK_PAUSE)
            thought = True
        await asyncio.sleep(delay)


async def settle(page, scroll: bool = True) -> None:
    """A moment of being on the page before acting on it: a small pointer
    drift and a short scroll, which is what a person does while reading."""
    try:
        x, y = _pos(page)
        await move_to(page, x + random.uniform(-140, 140),
                      y + random.uniform(-90, 90))
        if scroll and random.random() < 0.7:
            await page.mouse.wheel(0, random.uniform(60, 260))
            await asyncio.sleep(random.uniform(0.2, 0.6))
            await page.mouse.wheel(0, -random.uniform(20, 120))
    except Exception:
        pass    # input hygiene is never worth failing a login over
    await asyncio.sleep(random.uniform(0.4, 1.3))
