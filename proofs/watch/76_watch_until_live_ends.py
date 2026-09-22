"""With no minutes given, the watch lasts exactly as long as the live.

"Blank" used to mean "until somebody presses Stop", which leaves the fleet
sitting on a finished broadcast until a person notices. Nobody can know in
advance how long a live runs, so the default is the broadcast itself: the
keeper ends the watch when the live is over, and a minutes value still bounds
it for anyone who wants that.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("watch until live ends")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

keeper = inspect.getsource(DriverManager._keep_watching)
if "_finished_lives" not in keeper:
    failures.append("watch until live ends: the keeper never asks whether the live "  # noqa: F821
                    "has finished, so a watch with no limit runs forever")
if "if deadline is None:" not in keeper:
    failures.append("watch until live ends: the end-of-live check is not tied to "  # noqa: F821
                    "the no-limit case")

ended_js = DriverManager._WATCH_ENDED_JS
for phrase in ("live video has ended", "LIVE"):
    if phrase not in ended_js:
        failures.append(f"watch until live ends: the page check ignores {phrase!r}")  # noqa: F821


class _Page:
    def __init__(self, ended):
        self._ended = ended

    async def evaluate(self, script):
        if isinstance(self._ended, Exception):
            raise self._ended
        return self._ended


class _Auto:
    def __init__(self, ended):
        self.page = _Page(ended)


ONE = "https://www.facebook.com/share/v/one/"
TWO = "https://www.facebook.com/share/v/two/"

m = DriverManager()
m.log = lambda message: None

# Every page on a live says it is over.
m._watch_autos = {"a": _Auto(True), "b": _Auto(True)}
m._watch_urls = {"a": ONE, "b": ONE}
if asyncio.run(m._finished_lives()) != {ONE}:
    failures.append("watch until live ends: a finished live was not detected")  # noqa: F821

# One page still playing keeps that live running.
m._watch_autos = {"a": _Auto(True), "b": _Auto(False)}
m._watch_urls = {"a": ONE, "b": ONE}
if asyncio.run(m._finished_lives()):
    failures.append("watch until live ends: the watch ended while a page was still "  # noqa: F821
                    "watching the broadcast")

# A page that cannot be asked is a broken viewer, not proof the live ended.
m._watch_autos = {"a": _Auto(True), "b": _Auto(RuntimeError("page closing"))}
m._watch_urls = {"a": ONE, "b": ONE}
if asyncio.run(m._finished_lives()):
    failures.append("watch until live ends: an unreachable page ended the watch "  # noqa: F821
                    "for everyone")

# Two lives at once: one ending must not touch the other.
m._watch_autos = {"a": _Auto(True), "b": _Auto(False)}
m._watch_urls = {"a": ONE, "b": TWO}
if asyncio.run(m._finished_lives()) != {ONE}:
    failures.append("watch until live ends: a live ending was not judged on its own "  # noqa: F821
                    "pages, so a second live would end with the first")

# No pages at all is not a finished live either.
m._watch_autos = {}
m._watch_urls = {}
if asyncio.run(m._finished_lives()):
    failures.append("watch until live ends: an empty watch reported the live over")  # noqa: F821

print("FAILED" if [f for f in failures if "watch until live ends" in f] else "ok")  # noqa: F821
