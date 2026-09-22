"""Whatever opens a page says whether that page is on screen.

Hiding a browser stopped meaning "headless" and started meaning "a real
window, minimised" - because both of Chromium's headless engines report
HeadlessChrome in the User-Agent, which is what Facebook answers with a
captcha (see proofs/85). That swap only works if every window the app opens
is actually put down, and if a window raised for a human is put back down
afterwards. `_hidden` is what carries that, and `_back_to_tile` is what
reads it.

So `_hidden` has to be set by everything that adopts a page. This was true
when the swap was made and then quietly stopped being true:
scripts/login_parallel.py minimised its window and never set the flag, so
the object reported itself visible while sitting in the taskbar. Nothing
failed, because that path happens to compute a captcha wait of zero and so
never raises the window it would then fail to lower. It was one changed
default away from leaving a window open on the operator's desktop.

An audit found that. An audit does not survive the next person, so:

  1. a method that adopts a page as its own must set _hidden
  2. a method that opens a throwaway page must NOT have to - it owns no
     window the rest of the object will reason about
  3. _hidden starts False, so an object that never says is treated as
     visible rather than silently skipping a minimise
  4. something still READS it, or the whole invariant is dead weight
  5. code that assembles an automation by hand, outside the class, says it
     too - that is exactly where it was missed
"""
import inspect
import pathlib
import re
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("every page declares its visibility")  # noqa: F821

from src.core.facebook_automation import FacebookAutomation  # noqa: E402


def _fail(msg):
    failures.append(f"page visibility: {msg}")  # noqa: F821


# 1 + 2. Adopting a page means assigning it to self.page after opening one.
# A method that opens a page and hands it straight back (an image download, a
# storage-state extraction) owns nothing the rest of the object will consult.
adopters, throwaway = [], []
for name, fn in inspect.getmembers(FacebookAutomation, predicate=inspect.isfunction):
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        continue
    if "new_page(" not in src:
        continue
    (adopters if "self.page =" in src else throwaway).append((name, src))

if not adopters:
    _fail("no method adopts a page any more; this proof is watching the "
          "wrong thing")

for name, src in adopters:
    if "self._hidden" not in src:
        _fail(f"{name}() adopts a page without saying whether its window is "
              f"on screen, so _back_to_tile cannot put it back down")

# Not a rule that quietly spreads: a throwaway page must stay exempt, or the
# next person satisfies this proof by setting a flag that means nothing.
for name, src in throwaway:
    if "self.page =" in src:
        _fail(f"{name}() was classed as throwaway but adopts a page")

# 3. The default has to be the safe one.
init = inspect.getsource(FacebookAutomation.__init__)
if not re.search(r"self\._hidden\s*=\s*False", init):
    _fail("__init__ does not default _hidden to False, so an object that "
          "never declares itself would be treated as already hidden")

# 4. A flag nothing reads is not an invariant.
readers = [n for n, f in inspect.getmembers(FacebookAutomation,
                                            predicate=inspect.isfunction)
           if "self._hidden" in inspect.getsource(f)
           and not re.search(r"self\._hidden\s*=", inspect.getsource(f))]
if not readers:
    _fail("nothing reads _hidden any more, so setting it is dead weight and "
          "a raised window is never put back down")

# 5. The class cannot police code that assembles an automation by hand, and
# that is precisely where it was missed. Any script that assigns .page onto
# an automation has to hide it or declare it.
for path in sorted((ROOT / "scripts").glob("*.py")):  # noqa: F821
    text = path.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"^\s*\w+\.page\s*=\s*(?!None)", text, re.M):
        continue
    # An ASSIGNMENT or a CALL, not the word. Checking for the bare substring
    # passed this proof on a file whose only remaining mention of _hidden was
    # the comment explaining why it had been set - which is exactly the shape
    # a careless edit leaves behind.
    declares = (re.search(r"^\s*\w+\._hidden\s*=\s*(?!None)", text, re.M)
                or re.search(r"await\s+\w+\.hide_window\s*\(", text))
    if not declares:
        _fail(f"scripts/{path.name} builds an automation by hand and never "
              f"says whether its window is on screen")

print("FAILED" if [f for f in failures if "page visibility" in f] else "ok")  # noqa: F821
