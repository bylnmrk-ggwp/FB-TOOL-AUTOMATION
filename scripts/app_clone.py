"""Our own app cloner for LDPlayer - no third-party app, no subscription.

A cloner app (Dual Space and friends) runs the cloned app inside its own
sandbox, shows adverts, and gates the useful number of clones behind a
subscription. It also sits between the app and the network, which means it
can observe everything the clone does - including the passwords typed into a
Facebook login. Paying for that is the smaller problem.

Android already does this, for free and without a middleman: every user has
its own data directory, so one installed APK holds one independent session
per user. The APK is shared, only the data is cloned, which is why this costs
almost nothing per clone.

The only thing in the way was the cap. UserManager reads it from the
fw.max_users property and falls back to a build resource that happens to be 4
on this image - not a licence, just a default. Root sets the property and the
cap moves at once, no framework restart: measured 4 -> 32 on LDPlayer 9.
Nothing is written into /system, so there is nothing to undo; the property is
re-applied on each run.

Usage:
    python scripts/app_clone.py list
    python scripts/app_clone.py add 8 --package com.facebook.lite
    python scripts/app_clone.py launch --user 11 --package com.facebook.lite
    python scripts/app_clone.py remove --user 11
    python scripts/app_clone.py remove --all
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.mobile.adb import Device  # noqa: E402

CLONE_PREFIX = "fbclone"


def _clones(dev: Device) -> list[tuple[int, str]]:
    return [(u, n) for u, n in dev.users() if n.startswith(CLONE_PREFIX)]


def cmd_list(dev: Device, args) -> int:
    print(f"device      : {dev.serial}")
    print(f"rooted      : {dev.rooted()}")
    print(f"clone limit : {dev.max_users()}  (Owner counts as one)")
    users = dev.users()
    print(f"users       : {len(users)}")
    for uid, name in users:
        tag = "Owner" if uid == 0 else ("clone" if name.startswith(CLONE_PREFIX)
                                        else "other")
        installed = (dev.installed(args.package, user=uid)
                     if args.package else "-")
        print(f"   user {uid:<4} {name:<14} {tag:<6} {args.package or ''} "
              f"installed={installed}")
    return 0


def cmd_add(dev: Device, args) -> int:
    wanted_total = args.count + 1                 # Owner holds one session
    cap = dev.raise_user_limit(wanted_total)
    if cap < wanted_total:
        print(f"the device allows {cap} sessions in total and {wanted_total} "
              f"were asked for; making what fits")
    existing = {n: u for u, n in _clones(dev)}
    made = []
    for n in range(1, min(args.count, cap - 1) + 1):
        name = f"{CLONE_PREFIX}{n}"
        uid = existing.get(name)
        if uid is None:
            uid = dev.create_user(name)
            made.append((uid, name))
            print(f"created {name} (user {uid})")
        if args.package:
            dev.install_existing_for_user(args.package, uid)
            # A user created by pm is STOPPED, and a stopped user resolves no
            # components at all - the app would be "installed" and unlaunchable.
            dev.start_user(uid)
            print(f"   {args.package} shared with user {uid}, user started")
    print(f"\nclones now: {len(_clones(dev))}  (limit {dev.max_users() - 1} "
          f"besides Owner)")
    return 0


def cmd_launch(dev: Device, args) -> int:
    # The display belongs to one user at a time and every tap and dump goes to
    # whoever is in front, so a clone has to be switched to, not just started.
    dev.switch_user(args.user)
    dev.launch(args.package, user=args.user)
    print(f"user {args.user} is in the foreground running {args.package}")
    return 0


def cmd_remove(dev: Device, args) -> int:
    targets = _clones(dev) if args.all else [(args.user, "")]
    if not targets or targets == [(None, "")]:
        print("nothing to remove (pass --user N or --all)")
        return 1
    if dev.current_user() in [u for u, _ in targets]:
        dev.switch_user(0)                # never delete the foreground user
    for uid, name in targets:
        dev.remove_user(uid)
        print(f"removed user {uid} {name}".rstrip())
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--serial", default="127.0.0.1:5555")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="show clones and the current limit")
    p.add_argument("--package", default="com.facebook.lite")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("add", help="create N clones and share an app with them")
    p.add_argument("count", type=int)
    p.add_argument("--package", default="com.facebook.lite")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("launch", help="bring one clone to the foreground")
    p.add_argument("--user", type=int, required=True)
    p.add_argument("--package", default="com.facebook.lite")
    p.set_defaults(fn=cmd_launch)

    p = sub.add_parser("remove", help="delete clones")
    p.add_argument("--user", type=int)
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_remove)

    args = ap.parse_args(argv)
    dev = Device(serial=args.serial)
    try:
        dev.connect()
    except Exception as e:  # noqa: BLE001
        print(f"Could not reach {args.serial}: {e}")
        return 1
    return args.fn(dev, args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
