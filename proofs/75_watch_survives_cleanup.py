"""The watching browser outlives the run that started it.

Its pages are the viewers: close them and the account stops watching. So the
batch's own cleanup must touch only the batch's handles, and only three
things may end a watch - the Stop button, a new watch replacing it, or
quitting the app.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("watch survives cleanup")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

def _code(func) -> str:
    """The function's code with its docstring removed - a docstring that
    explains what is NOT touched must not read as touching it."""
    import ast
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    body = tree.body[0].body
    first = body[0] if body else None
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        body = body[1:]
    return "\n".join(ast.unparse(node) for node in body)


cleanup = _code(DriverManager._cleanup_batch)
for handle in ("_watch_pw", "_watch_browser", "_watch_autos", "_stop_watch"):
    if handle in cleanup:
        failures.append(f"watch survives cleanup: _cleanup_batch touches {handle}, "  # noqa: F821
                        f"so finishing a run would close the viewers")

general = _code(DriverManager._do_cleanup)
if "_stop_watch" in general:
    failures.append("watch survives cleanup: the cleanup command stops the watch, "  # noqa: F821
                    "so any teardown ends the viewing")

# A batch that follows a watch must not end it either.
batch = _code(DriverManager._do_batch)
if "_stop_watch" in batch:
    failures.append("watch survives cleanup: a queue run stops the watch")  # noqa: F821

# Handles really are separate objects.
m = DriverManager()
m.log = lambda message: None
m._watch_pw = object()
m._watch_browser = object()
m._watch_autos = {"someone": object()}
m._batch_automations = {}
m._batch_pw = None
kept = (m._watch_pw, m._watch_browser, dict(m._watch_autos))
asyncio.run(m._cleanup_batch())
if (m._watch_pw, m._watch_browser, m._watch_autos) != kept:
    failures.append("watch survives cleanup: batch cleanup cleared the watch "  # noqa: F821
                    "handles")

# Only the three deliberate paths stop it.
for name in ("_do_quit",):
    if "_stop_watch" not in inspect.getsource(getattr(DriverManager, name)):
        failures.append(f"watch survives cleanup: {name} leaves the watch running, "  # noqa: F821
                        f"so the browser outlives the app")
if "_stop_watch" not in inspect.getsource(DriverManager._do_watch):
    failures.append("watch survives cleanup: a new watch does not replace the old "  # noqa: F821
                    "one, so pages would pile up")

print("FAILED" if [f for f in failures if "watch survives cleanup" in f] else "ok")  # noqa: F821
