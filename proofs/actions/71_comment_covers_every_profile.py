"""Every profile gets a comment, even with fewer lines than accounts.

Comment lines were dealt one per profile and then stopped: 49 lines against
53 profiles queued 49 items, and four accounts sat out the post without a
word in the log. The lines now rotate, so the queue always holds one item per
profile.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("comment covers every profile")  # noqa: F821

from src.ui.queue_tab import QueueTab  # noqa: E402

URL = "https://www.facebook.com/share/p/19GsMJaoiZ/"
PROFILES = [f"acct{i}@example.com" for i in range(53)]
LINES = "\n".join(f"Comment number {i}" for i in range(49))

items = QueueTab._build_comment_items(None, LINES, URL, PROFILES)
if len(items) != len(PROFILES):
    failures.append(f"comment covers every profile: {len(items)} item(s) for "  # noqa: F821
                    f"{len(PROFILES)} profiles - {len(PROFILES) - len(items)} "
                    f"account(s) would sit the post out")
covered = {i["profile_name"] for i in items}
missing = [p for p in PROFILES if p not in covered]
if missing:
    failures.append(f"comment covers every profile: no item for {missing[:4]}")  # noqa: F821
if any(not (i.get("comment_text") or "").strip() for i in items):
    failures.append("comment covers every profile: an item has no comment text")  # noqa: F821

# One plain comment still goes to everyone, unchanged.
one = QueueTab._build_comment_items(None, "Interested po", URL, PROFILES)
if len(one) != len(PROFILES) or {i["comment_text"] for i in one} != {"Interested po"}:
    failures.append("comment covers every profile: a single comment no longer "  # noqa: F821
                    "applies to every profile")

# More lines than profiles: still one item per profile, no duplicates.
many = QueueTab._build_comment_items(
    None, "\n".join(f"line {i}" for i in range(80)), URL, PROFILES[:10])
if len({i["profile_name"] for i in many}) != 10:
    failures.append(f"comment covers every profile: {len(many)} item(s) for 10 "  # noqa: F821
                    f"profiles when lines outnumber accounts")

print("FAILED" if [f for f in failures if "comment covers every profile" in f] else "ok")  # noqa: F821
