"""A fleet too large for one PC is divided between several, without a list.

One machine holds about 37 watching pages - 18 GB of RAM, 2 GB left for
Windows, 315 MB per page measured - and a fleet of 122 does not fit. Each PC
is told which machine it is out of how many and takes its own share: sort the
names, take every Nth. No machine needs to know what the others do, nothing
has to be kept in step by hand, and adding a machine re-divides the fleet
with no name assigned twice or dropped.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("machine share")  # noqa: F821

from src.core import fleet  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402

NAMES = [f"acct{i:03d}" for i in range(122)]
_saved = (cfg.get_setting(fleet.INDEX_KEY, None), cfg.get_setting(fleet.COUNT_KEY, None))

try:
    # One machine owns everything - what a single-PC setup gets by default.
    fleet.set_share(1, 1)
    if fleet.mine(NAMES) != sorted(NAMES):
        failures.append("machine share: a single machine does not own the whole fleet")  # noqa: F821

    # Three machines: no overlap, nothing dropped, sizes within one.
    groups = []
    for index in (1, 2, 3):
        fleet.set_share(index, 3)
        groups.append(set(fleet.mine(NAMES)))
    covered = set().union(*groups)
    if covered != set(NAMES):
        failures.append(f"machine share: {len(set(NAMES) - covered)} account(s) belong "  # noqa: F821
                        f"to no machine")
    for a in range(3):
        for b in range(a + 1, 3):
            shared = groups[a] & groups[b]
            if shared:
                failures.append(f"machine share: machines {a+1} and {b+1} both own "  # noqa: F821
                                f"{len(shared)} account(s)")
    sizes = sorted(len(g) for g in groups)
    if sizes[-1] - sizes[0] > 1:
        failures.append(f"machine share: the split is uneven: {sizes}")  # noqa: F821

    # Nonsense settings mean "own everything", never "own nothing".
    for index, count in ((0, 0), (5, 3), (-1, 2), (1, 0)):
        cfg.save_setting(fleet.INDEX_KEY, index)
        cfg.save_setting(fleet.COUNT_KEY, count)
        got_index, got_count = fleet.share()
        if not (1 <= got_index <= got_count):
            failures.append(f"machine share: {index} of {count} came back as "  # noqa: F821
                            f"{got_index} of {got_count}")
        if not fleet.mine(NAMES):
            failures.append(f"machine share: {index} of {count} left this machine "  # noqa: F821
                            f"with no accounts at all")

    # The share is what the rest of the app sees, so one setting moves the
    # queue, the watch and the login run together.
    listing = inspect.getsource(cfg.list_profiles_for_browser)
    if "fleet" not in listing:
        failures.append("machine share: the profile listing ignores the share, so a "  # noqa: F821
                        "machine would still drive the whole fleet")

    # A machine keeps most of its accounts when the fleet grows.
    fleet.set_share(2, 3)
    before = set(fleet.mine(NAMES))
    after = set(fleet.mine(NAMES + [f"acct{i:03d}" for i in range(122, 134)]))
    kept = len(before & after) / max(1, len(before))
    if kept < 0.5:
        failures.append(f"machine share: growing the fleet moved {100 * (1 - kept):.0f}% "  # noqa: F821
                        f"of this machine's accounts to other PCs")
finally:
    if _saved[0] is None:
        conf = cfg._load_config()
        conf.pop(fleet.INDEX_KEY, None)
        conf.pop(fleet.COUNT_KEY, None)
        cfg._save_config(conf)
    else:
        cfg.save_setting(fleet.INDEX_KEY, _saved[0])
        cfg.save_setting(fleet.COUNT_KEY, _saved[1])

print("FAILED" if [f for f in failures if "machine share" in f] else "ok")  # noqa: F821
