"""Comment on one Facebook post from many banked Facebook Lite sessions.

Each account's session is restored into Owner, the post is opened by URL, and
the comment is typed into the permalink view's compose box and sent. Unlike
the scrolling feed - a blank canvas to uiautomator - a post's permalink view
exposes real nodes, so the comment box and its text can be driven.

One session is live at a time: restore, comment, restore the next. The banked
tarballs are the source and are never consumed, so a run can be repeated.

This posts PUBLIC comments. It types only the text given on the command line,
from only the accounts named, and reports what each one did.

Usage:
    python scripts/fblite_comment.py --post <url> --text "up" --dry-run
    python scripts/fblite_comment.py --post <url> --text "up" --count 3
    python scripts/fblite_comment.py --post <url> --text "up"          # all banked
    python scripts/fblite_comment.py --post <url> --text "up" --only <fbid> <fbid>
"""
import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.mobile.adb import Device, find  # noqa: E402
from src.mobile import session_bank  # noqa: E402

PACKAGE = "com.facebook.lite"

# The compose bar's send control carries no text or content-desc, so it is not
# findable by label. The instance runs at a fixed 540x960, where the send
# arrow sits at the far right of the bar - this point lands on it.
SEND_XY = (493, 915)


def _human(a: float = 0.6, b: float = 1.8) -> None:
    time.sleep(random.uniform(a, b))


def open_post(dev: Device, url: str, log=print) -> bool:
    """Open the post's permalink in Facebook Lite, past the app chooser."""
    dev.stop(PACKAGE)
    dev.shell(f'am start -a android.intent.action.VIEW -d "{url}" {PACKAGE}')
    # Android's "Open with" resolver appears when more than one app claims the
    # link. Pick Facebook Lite, once.
    deadline = time.time() + 40
    while time.time() < deadline:
        nodes = dev.screen()
        blob = " ".join((n.text or n.desc).lower() for n in nodes)
        if "open with" in blob or "lite" in blob and "just once" in blob:
            lite = [n for n in nodes if (n.text or n.desc).strip().lower() == "lite"]
            if lite:
                dev.tap_node(lite[0]); _human()
            once = find(dev.screen(), text="Just once") + find(dev.screen(), desc="Just once")
            if once:
                dev.tap_node(once[0])
            time.sleep(6)
            continue
        # In the post yet? The compose box is the reliable marker.
        if any("write a comment" in (n.text or n.desc).lower() for n in nodes):
            return True
        time.sleep(3)
    return any("write a comment" in (n.text or n.desc).lower()
               for n in dev.screen())


def comment_once(dev: Device, url: str, text: str, log=print) -> tuple[str, str]:
    """Restore is the caller's job. Open the post and leave the comment."""
    if not dev.can_type(text):
        return "skipped", "the comment text holds characters adb cannot type"
    if not open_post(dev, url, log=log):
        return "no post", "the post's compose box never appeared"

    box = [n for n in dev.screen()
           if "write a comment" in (n.text or n.desc).lower()]
    if not box:
        return "no post", "no comment box on the permalink view"
    dev.tap_node(box[0]); _human(1.0, 2.2)
    dev.type_text(text); _human(0.8, 1.6)

    # The send arrow only appears once there is text; tap it by position.
    dev.tap(*SEND_XY)

    # After a send, the compose box empties back to its "Write a comment..."
    # hint and the comment renders in the list a beat later. Poll for either:
    # the text appearing near a name, or the box no longer holding the typed
    # text. Reading once, too soon, sees neither and reports a false miss.
    deadline = time.time() + 20
    while time.time() < deadline:
        nodes = dev.screen()
        if any(text.lower() == (n.text or n.desc).strip().lower()
               for n in nodes):
            return "ok", "comment posted"
        # Compose box back to its empty hint, with the typed text gone from
        # every input: the send cleared the field, i.e. it went through.
        hint = any("write a comment" in (n.text or n.desc).lower()
                   for n in nodes)
        typed_still_there = any(
            n.cls.endswith(("EditText", "MultiAutoCompleteTextView"))
            and text.lower() in (n.text or "").lower() for n in nodes)
        if hint and not typed_still_there:
            return "ok", "comment sent (compose box cleared)"
        time.sleep(3)
    return "unsure", "sent, but not confirmed on the post"


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="127.0.0.1:5555")
    ap.add_argument("--post", required=True, help="the post URL to comment on")
    ap.add_argument("--text", required=True, help="the comment to leave")
    ap.add_argument("--only", nargs="*", metavar="FBID", default=None,
                    help="comment only from these banked fb ids")
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    banked = session_bank.banked()
    fbids = list(args.only) if args.only else list(banked.keys())
    if args.count is not None:
        fbids = fbids[:args.count]
    if not fbids:
        print("No banked sessions to comment from.")
        return 0

    print(f"Post    : {args.post}")
    print(f"Comment : {args.text!r}")
    print(f"Accounts: {len(fbids)}")
    for fbid in fbids:
        who = (banked.get(fbid) or {}).get("username", "?")
        print(f"   {fbid}  ({who})")
    if args.dry_run:
        print("\n--dry-run: nothing was posted.")
        return 0

    dev = Device(serial=args.serial)
    try:
        dev.connect()
    except Exception as e:  # noqa: BLE001
        print(f"Could not reach {args.serial}: {e}")
        return 1

    results: dict[str, list[str]] = {}
    for i, fbid in enumerate(fbids, 1):
        who = (banked.get(fbid) or {}).get("username", fbid)
        print(f"\n[{i}/{len(fbids)}] {who} ({fbid})")
        try:
            if not session_bank.restore_session(dev, fbid, PACKAGE):
                print("    could not restore this session")
                results.setdefault("restore failed", []).append(fbid)
                continue
            verdict, detail = comment_once(dev, args.post, args.text, log=print)
        except Exception as e:  # noqa: BLE001 - one account must not end the run
            verdict, detail = "error", f"{type(e).__name__}: {e}"
        print(f"    {verdict}: {detail}")
        results.setdefault(verdict, []).append(fbid)
        # A human pause between accounts: a burst of identical comments in
        # seconds is the clearest spam signal there is.
        if i < len(fbids):
            time.sleep(random.uniform(6, 15))

    print("\n" + "=" * 60)
    for verdict, ids in sorted(results.items()):
        print(f"  {verdict}: {len(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
