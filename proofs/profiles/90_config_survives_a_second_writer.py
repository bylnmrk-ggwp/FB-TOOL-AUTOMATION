"""A config write must not resurrect what another process deleted.

config.json is written by more than one process at a time: the FastAPI
server, the driver worker, and any script run from a shell. Every writer
used to send the WHOLE dictionary back - a copy read up to two seconds
earlier, because _load_config caches. So a long-running server that saved
one setting also wrote back every profile it still remembered, undoing
deletions another process had already committed to disk.

That is how 23 profiles came back after their Brave directories had been
removed: the names returned, the directories did not, and the fleet was
left pointing at paths that no longer exist.

A writer must re-read the file, apply only its own change, and write that.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("config survives a second writer")  # noqa: F821

from src.storage import config_manager as cfg  # noqa: E402

_saved_file = cfg.CONFIG_FILE
_tmp = Path(tempfile.mkdtemp(prefix="cfgproof"))
cfg.CONFIG_FILE = _tmp / "config.json"


def _write_on_disk(config: dict) -> None:
    """A second process writing the file behind this one's back."""
    cfg.CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _on_disk() -> dict:
    return json.loads(cfg.CONFIG_FILE.read_text(encoding="utf-8"))


try:
    # This process reads a config holding three profiles, so its cache now
    # remembers all three.
    _write_on_disk({"profiles": {"a": "/p/a", "b": "/p/b", "c": "/p/c"}})
    cfg._config_cache = None
    if sorted(cfg.list_profiles()) != ["a", "b", "c"]:
        failures.append("config writer: the three starting profiles did not load")  # noqa: F821

    # Another process deletes 'b' and commits that to disk. This process is
    # not told, and its cache is still inside the TTL.
    _write_on_disk({"profiles": {"a": "/p/a", "c": "/p/c"}})

    # This process now saves a profile of its own.
    cfg.save_profile("d", "/p/d")

    after = _on_disk().get("profiles", {})
    if "b" in after:
        failures.append("config writer: save_profile resurrected 'b', which another "  # noqa: F821
                        "process had already deleted")
    if "d" not in after:
        failures.append("config writer: save_profile did not write its own profile 'd'")  # noqa: F821
    for name in ("a", "c"):
        if name not in after:
            failures.append(f"config writer: save_profile dropped '{name}', which it "  # noqa: F821
                            f"was not asked to touch")

    # The same in the other direction: a delete must survive a second
    # process that added a profile in the meantime.
    _write_on_disk({"profiles": {"a": "/p/a", "c": "/p/c", "d": "/p/d"}})
    cfg._config_cache = None
    cfg.list_profiles()                       # warm this process's cache
    _write_on_disk({"profiles": {"a": "/p/a", "c": "/p/c", "d": "/p/d",
                                 "e": "/p/e"}})   # the other process adds 'e'
    cfg.delete_profile("d")

    after = _on_disk().get("profiles", {})
    if "d" in after:
        failures.append("config writer: delete_profile did not remove 'd'")  # noqa: F821
    if "e" not in after:
        failures.append("config writer: delete_profile erased 'e', which another "  # noqa: F821
                        "process had just added")

    # A setting write must leave the profiles map exactly as it found it.
    cfg._config_cache = None
    cfg.get_setting("anything", None)          # warm the cache again
    _write_on_disk({"profiles": {"a": "/p/a"}, "settings": {}})
    cfg.save_setting("sheet_sync", False)

    after = _on_disk()
    if sorted(after.get("profiles", {})) != ["a"]:
        failures.append("config writer: save_setting rewrote the profiles map from a "  # noqa: F821
                        "stale copy")
    if after.get("settings", {}).get("sheet_sync") is not False:
        failures.append("config writer: save_setting did not store its own setting")  # noqa: F821
finally:
    cfg.CONFIG_FILE = _saved_file
    cfg._config_cache = None
