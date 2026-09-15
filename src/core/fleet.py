"""Splitting one account fleet across several PCs.

One machine holds about 37 watching pages: 18 GB of RAM, 2 GB left for
Windows, 315 MB per page measured. A fleet of 122 does not fit, and opening
more than fits is worse than opening fewer - a machine in swap plays no video
at all.

So the fleet is divided by machine. Each PC is told "you are machine 2 of 3"
and takes its own third of the accounts, deterministically: sort the profile
names, then take every Nth. No machine needs to know what the others are
doing, no list has to be kept in step by hand, and adding a machine
re-divides everything without a single name being assigned twice or missed.

Set the count to 1 and a machine owns the whole fleet again, which is what a
single-PC setup gets without touching anything.
"""
from src.storage import config_manager as cfg

INDEX_KEY = "machine_index"     # 1-based: machine 1 of N
COUNT_KEY = "machine_count"


def share() -> tuple[int, int]:
    """(this machine's number, how many machines share the fleet).

    Always sane: a count below 1, or an index outside it, means one machine
    owning everything rather than a machine owning nothing.
    """
    try:
        count = int(cfg.get_setting(COUNT_KEY, 1) or 1)
    except (TypeError, ValueError):
        count = 1
    try:
        index = int(cfg.get_setting(INDEX_KEY, 1) or 1)
    except (TypeError, ValueError):
        index = 1
    if count < 1:
        count = 1
    if not (1 <= index <= count):
        index = 1
    return index, count


def set_share(index: int, count: int) -> tuple[int, int]:
    """Record which machine this is. Returns what was actually stored."""
    count = max(1, int(count))
    index = min(max(1, int(index)), count)
    cfg.save_setting(COUNT_KEY, count)
    cfg.save_setting(INDEX_KEY, index)
    return index, count


def mine(names) -> list:
    """The share of `names` that belongs to this machine.

    Round-robin over the sorted names rather than contiguous blocks: the
    slices stay the same size to within one whichever way the fleet grows,
    and a name keeps its machine when others are added around it far more
    often than a block split would allow.
    """
    index, count = share()
    ordered = sorted(names)
    if count <= 1:
        return ordered
    return [name for position, name in enumerate(ordered)
            if position % count == index - 1]


def describe(total: int | None = None) -> str:
    """One line for the UI: which machine this is, and how much it owns."""
    index, count = share()
    if count <= 1:
        return "All accounts on this PC"
    if total is None:
        return f"Machine {index} of {count}"
    return f"Machine {index} of {count} - {len(mine(range(total)))} of {total} accounts"
