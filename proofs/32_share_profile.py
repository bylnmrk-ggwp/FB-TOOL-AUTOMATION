"""Proof (BUG 3): single-profile share must record history under a real profile.

_do_share_to_groups read profile_name = cmd.get("profile", ""), but no
producer ever sets a "profile" key, so db.has_shared / db.record_share ran
with "". The handler always shares on the first saved profile (the same one
_auto_launch_first_profile() launches), so the name is resolved from
cfg.list_profiles()[0], guarded for empty.

No browser, no Google, no Brave dir: the automation is a stub whose
share_post_to_group succeeds, cfg/db are monkeypatched, and the worker
thread is never started.
"""
import asyncio
import sys

sys.path.insert(0, str(ROOT))

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.core import driver_manager as _dm  # noqa: E402

step("single share records a non-empty profile")

_KNOWN = "VERIFYSHARE1"
_RECORDS = []  # profile names passed to db.record_share


class _FakeAuto:
    def __init__(self):
        self.context = object()  # truthy -> skip auto-launch

    async def share_post_to_group(self, post_url, group_name,
                                  comment_text=None, reaction=None,
                                  skip_timeline=False, skip_reaction=False):
        return True, "shared"

    async def cleanup(self):
        return None


_orig = {
    "list_profiles": _dm.cfg.list_profiles,
    "has_shared": _dm.db.has_shared,
    "record_share": _dm.db.record_share,
}

try:
    _dm.cfg.list_profiles = lambda: [_KNOWN, "OTHER"]
    _dm.db.has_shared = lambda profile, post_url, target: False
    _dm.db.record_share = lambda profile, *a, **k: _RECORDS.append(profile)

    _m = _DM(log_callback=lambda msg: None)
    _m._automation = _FakeAuto()

    asyncio.run(_m._do_share_to_groups({
        "type": "share_to_groups",
        "post_url": "https://facebook.com/posts/1",
        "groups": [{"name": "Group One", "url": "gu1"}],
        "comment_text": None,
        "reaction": None,
    }))

    if not _RECORDS:
        failures.append("single share: db.record_share was never called")
    elif any(not p for p in _RECORDS):
        failures.append(
            f"single share: record_share got an empty profile name (records={_RECORDS})")
    elif _RECORDS[0] != _KNOWN:
        failures.append(
            f"single share: expected profile '{_KNOWN}', got '{_RECORDS[0]}'")
finally:
    _dm.cfg.list_profiles = _orig["list_profiles"]
    _dm.db.has_shared = _orig["has_shared"]
    _dm.db.record_share = _orig["record_share"]

print("ok" if not [f for f in failures if f.startswith("single share")] else "FAILED")
