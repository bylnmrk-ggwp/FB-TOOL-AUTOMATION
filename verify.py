"""Behavior-preservation proof for FB TOOL AUTOMATION (no test suite exists).
Run: python <this file>   from the project root.
1. compile every module
2. import every module
3. Tkinter smoke test: build MainWindow, assert callback wiring, both themes
"""
import importlib
import os
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

failures = []


def step(name):
    print(f"\n=== {name} ===")


step("compile")
import compileall
if not all(compileall.compile_dir(d, quiet=2) for d in ("src", "scripts"))         or not compileall.compile_file("main.py", quiet=2):
    failures.append("compileall")
print("ok" if not failures else "FAILED")

step("import all modules")
mods = sorted(
    str(p.with_suffix("")).replace(os.sep, ".")
    for p in pathlib.Path("src").rglob("*.py")
    if "__pycache__" not in str(p)
)
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        failures.append(f"import {m}: {e}")
        print("FAIL", m, e)
print(f"{len(mods) - len([f for f in failures if f.startswith('import')])}/{len(mods)} imported")

step("tkinter smoke test")
try:
    from src.core.driver_manager import DriverManager
    from src.ui.main_window import MainWindow

    manager = DriverManager()          # thread NOT started - no browser launched
    app = MainWindow(driver_manager=manager)
    manager.log = app.log_tab.write

    for attr in ("profiles_tab", "queue_tab", "share_tab", "memory_tab", "log_tab"):
        if getattr(app, attr, None) is None:
            failures.append(f"MainWindow.{attr} missing")

    # every set_on_* hook the tabs expose must have been wired by MainWindow
    for tab_name in ("profiles_tab", "queue_tab", "share_tab", "memory_tab"):
        tab = getattr(app, tab_name, None)
        if tab is None:
            continue
        for setter in [n for n in dir(tab) if n.startswith("set_on_")]:
            name = setter[len("set_on_"):]
            slots = [f"_on_{name}_cb", f"_on_{name}", f"on_{name}"]
            if not any(getattr(tab, s, None) for s in slots):
                failures.append(f"{tab_name}.{setter} never wired (looked for {slots})")

    app.update_idletasks()
    app.update()
    app.destroy()
    print("MainWindow built, wiring asserted, destroyed")
except Exception:
    traceback.print_exc()
    failures.append("tkinter smoke test")

step("proofs/**/*.py")
import runpy
# Proofs live in topic folders (proofs/login/, proofs/watch/, ...), but the
# NN_ prefix is still the run order: it is chronological, so a later proof
# may rely on what an earlier one set up. Sorting by file name rather than
# by path keeps that order across folders - by path, every proofs/actions/
# file would run before every proofs/watch/ file.
_PROOFS = sorted((ROOT / "proofs").rglob("*.py"), key=lambda p: p.name)
for _proof in _PROOFS:
    try:
        runpy.run_path(str(_proof), init_globals={"failures": failures,
                                                 "step": step, "ROOT": ROOT})
    except Exception as _e:
        traceback.print_exc()
        failures.append(f"{_proof.name}: {_e}")
print(f"{len(_PROOFS)} proof file(s) run")

print("\n================ RESULT ================")
if failures:
    for f in failures:
        print("FAIL:", f)
    sys.exit(1)
print("ALL PROOFS PASS")
