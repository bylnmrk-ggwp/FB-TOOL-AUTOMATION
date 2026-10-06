"""Listing this browser's profiles does not re-resolve every path each call.

The status bar refreshes on a 100 ms tick, and each refresh counted the
profiles by calling list_profiles_for_browser, which resolved every saved
profile path through the filesystem. At 3157 profiles that is 2.3 s of
realpath syscalls per call, on the Tk thread - so the thread never went idle
and the window never mapped. Nothing rendered: no tiles, no live-viewer
counts, nothing.

A path's resolved location does not change between ticks, so it is resolved
once and remembered. Repeated calls cost a dict lookup per profile; only a
newly added path is resolved. The root is resolved once as well.
"""
import sys
import pathlib

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("profile list is cached")  # noqa: F821

from src.storage import config_manager as cfg  # noqa: E402
from src.core import browser_choice as bc  # noqa: E402
from src.core import fleet  # noqa: E402

ROOT_DIR = r"C:/Users/verify/AppData/Local/BraveSoftware/Brave-Browser/User Data"

# Three under the Brave root, two outside it. Only the three under it count.
PROFILES = {
    "A": ROOT_DIR + "/Default",
    "B": ROOT_DIR + "/Profile 1",
    "C": ROOT_DIR + "/Profile 2",
    "X": r"C:/Users/verify/AppData/Local/Chromium/User Data/Default",
    "Y": r"D:/somewhere/else",
}

_real_resolve = pathlib.Path.resolve
_real_load = cfg._load_config
_real_root = bc.user_data_root
_real_share = fleet.share
_calls = {"n": 0}


def _counting_resolve(self, *a, **k):
    _calls["n"] += 1
    return _real_resolve(self, *a, **k)


try:
    pathlib.Path.resolve = _counting_resolve
    bc.user_data_root = lambda: pathlib.Path(ROOT_DIR)
    fleet.share = lambda: (1, 1)          # single PC: mine() returns them all
    _cfg = {"profiles": dict(PROFILES)}
    cfg._load_config = lambda: _cfg

    # Start from a cold cache, the state at process launch.
    cfg._resolve_cache.clear()

    # 1. First call resolves each distinct path once plus the root, and
    #    returns only the three names under the Brave root.
    _calls["n"] = 0
    first = cfg.list_profiles_for_browser()
    c1 = _calls["n"]
    if sorted(first) != ["A", "B", "C"]:
        failures.append(  # noqa: F821
            f"profile list is cached: wrong names, got {sorted(first)}")
    if c1 == 0:
        failures.append(  # noqa: F821
            "profile list is cached: the first call resolved nothing - the "
            "test did not exercise the resolve path")

    # 2. A second call with the same config resolves nothing more.
    _calls["n"] = 0
    second = cfg.list_profiles_for_browser()
    if _calls["n"] != 0:
        failures.append(  # noqa: F821
            f"profile list is cached: a repeat call re-resolved "
            f"{_calls['n']} path(s); it must serve the cache (0)")
    if sorted(second) != ["A", "B", "C"]:
        failures.append(  # noqa: F821
            f"profile list is cached: repeat call gave {sorted(second)}")

    # 3. Adding one profile resolves exactly that one new path - not the
    #    whole map, and not the already-resolved root.
    _cfg["profiles"]["D"] = ROOT_DIR + "/Profile 3"
    _calls["n"] = 0
    third = cfg.list_profiles_for_browser()
    if _calls["n"] != 1:
        failures.append(  # noqa: F821
            f"profile list is cached: adding one profile resolved "
            f"{_calls['n']} path(s); only the new one should resolve (1)")
    if sorted(third) != ["A", "B", "C", "D"]:
        failures.append(  # noqa: F821
            f"profile list is cached: after add got {sorted(third)}")
finally:
    pathlib.Path.resolve = _real_resolve
    cfg._load_config = _real_load
    bc.user_data_root = _real_root
    fleet.share = _real_share
    cfg._resolve_cache.clear()

print("FAILED" if [f for f in failures  # noqa: F821
                   if "profile list is cached" in f] else "ok")
