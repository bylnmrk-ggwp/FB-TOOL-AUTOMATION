"""Proof: the bulk commands carry an explicit profile list (plan Task 9).

DriverManager() is built without start(), so there is no worker thread and
no browser. Each bulk helper must accept profile_names= and put it on the
command dict unchanged; the handlers then read
cmd.get("profile_names") or cfg.list_profiles(), so a page that knows which
rows are checked can scope a run without the handler re-deriving the set.
"""
import asyncio
import inspect
import queue as _q
import sys

sys.path.insert(0, str(ROOT))

from src.core.driver_manager import DriverManager as _DM  # noqa: E402

step("profile_names on bulk commands")
_m = _DM()
_m.share_to_groups_bulk("u", [], profile_names=["P1"])
_m.join_group(["g"], profile_names=["P1"])
_m.fetch_my_groups_bulk(profile_names=["P1"])
_m.auto_setup_all_profiles(profile_names=["P1"])
_m.accept_all_pending_requests(profile_names=["P1"])
_m.watch_url("u", None, profile_names=["P1"])
_seen = 0
while True:
    try:
        _c = _m.cmd_queue.get_nowait()
    except _q.Empty:
        break
    _seen += 1
    if _c.get("profile_names") != ["P1"]:
        failures.append(f"{_c['type']} dropped profile_names")
if _seen != 6:
    failures.append(f"profile_names: expected 6 queued commands, got {_seen}")

# The dispatcher must hand the list to _do_watch as its third argument; the
# handler keeps the logged-in ('ok') filter on top, so a name that is not
# active is still never opened.
if "profile_names" not in inspect.signature(_DM._do_watch).parameters:
    failures.append("profile_names: _do_watch does not accept profile_names")
if 'cmd.get("profile_names")' not in inspect.getsource(_DM._async_run):
    failures.append("profile_names: watch_url dispatch does not pass profile_names")

# share_to_groups_bulk intersects each group's profile list with the request.
# A request that matches no group profile must stop before any browser is
# launched, reporting that no profile matched (not "no groups selected").
_m2 = _DM(log_callback=lambda m: None)
asyncio.run(_m2._do_share_to_groups_bulk({
    "type": "share_to_groups_bulk", "post_url": "u",
    "groups": [{"name": "g", "url": "gu", "profiles": ["P1", "P2"]}],
    "comment_text": None, "reaction": None,
    "profile_names": ["P3"],
}))
try:
    _r = _m2.result_queue.get_nowait()
except _q.Empty:
    _r = None
if not _r or _r.get("type") != "share_bulk_result" or _r.get("ok") is not False \
        or "No profiles found" not in (_r.get("error") or ""):
    failures.append(f"profile_names: share_to_groups_bulk did not intersect: {_r}")

print("ok" if not [f for f in failures if "profile_names" in f] else "FAILED")
