"""Log roster accounts into Facebook Lite, one at a time, inside LDPlayer.

This does NOT feed the browser fleet. Facebook Lite keeps its session in
app-private storage; every browser path in this app reads c_user/xs cookies
(state_cache.py, login_accounts.py). An account logged in here works inside
Facebook Lite and nowhere else.

For the same reason nothing here writes accounts.status or
accounts.status_reason. Those columns mean "what the BROWSER session is", and
scripts/login_accounts.py --challenges reads them to decide which accounts
still need a person. Writing an app verdict into them would quietly corrupt
that queue, so this reports to the screen and leaves the roster alone.

One device holds one Facebook Lite session at a time. --clear wipes the app
between accounts, which DESTROYS the session already there - it is off by
default and has to be asked for.

Usage:
    python scripts/fblite_login.py --dry-run          # who would be attempted
    python scripts/fblite_login.py --only <username>  # one account
    python scripts/fblite_login.py --count 1          # the first account
    python scripts/fblite_login.py --count 5 --clear  # five, wiping between
"""
import argparse
import re
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

PACKAGE = "com.facebook.lite"

# Facebook Lite renames its view ids between releases and localises every
# label, so nothing is matched on one id alone. The password field is found by
# its password flag, which is a property of the field and not of the language.
USERNAME_HINTS = ("email", "phone", "mobile", "username")
LOGIN_HINTS = ("log in", "login", "log-in", "sign in")

# What the screen says once it is no longer the login form. Facebook Lite 529
# labels almost nothing - uiautomator returns bare nodes with empty text for
# the whole onboarding run - but the feed's search box is labelled, so it is
# the one reliable "we are in" marker.
GOOD = ("search...", "what's on your mind", "news feed", "marketplace",
        "your liked posts", "people you may know")

# After a successful login Facebook Lite walks a chain of setup screens, and
# Google adds one of its own on top. Measured on 529.0.0.7.105, in order:
# Google "Save login info?", "Access to contacts" (plus an "are you sure"
# confirm), "Add email", a language offer, "Add friends", "Access to location".
#
# Facebook Lite 529 renders its feed on a canvas: uiautomator returns nodes
# with NO text for the whole signed-in app, so "what does the screen say" can
# not tell a live session from a dead one. What it CAN see is the login form,
# because EditText fields are real views. So the test is the absence of that
# form, not the presence of a feed.
#
# The onboarding chain after a login is answered with BACK, never with taps at
# remembered coordinates. Blind taps were tried first and pressed "Upload
# contacts" on an account, because that screen's layout differs from the one
# the coordinates were measured on. BACK can only ever go backwards: it cannot
# press Upload, Continue, or Add friend. Backing out drops to the launcher and
# the session stays saved, which is all that is wanted.


def on_login_form(dev: Device) -> bool:
    """Whether the login form is up - the one thing uiautomator can see."""
    nodes = dev.screen()
    if find(nodes, password=True):
        return True
    blob = " ".join((n.text or n.desc).lower() for n in nodes)
    return "mobile number or email" in blob


def leave_onboarding(dev: Device, user: int | None = None,
                     rounds: int = 10, log=print) -> bool:
    """Back out of the post-login setup screens, accepting nothing.

    Returns True when the app is no longer showing the login form, i.e. the
    session took.
    """
    for _ in range(rounds):
        dev.key("KEYCODE_BACK")
        time.sleep(3)
        foc = dev.shell("dumpsys window | grep mCurrentFocus")
        if PACKAGE not in foc:                  # dropped out to the launcher
            break
    dev.stop(PACKAGE, user=user)
    time.sleep(2)
    dev.launch(PACKAGE, user=user)
    time.sleep(12)
    return not on_login_form(dev)


CHALLENGE = ("not a robot", "captcha", "security check",
             "two-factor", "authentication", "checkpoint")
REJECTED = ("incorrect", "wrong password", "invalid", "didn't match",
            "isn't connected", "couldn't find")


def classify(labels: list[str]) -> tuple[str, str]:
    """(verdict, detail) from everything written on the screen."""
    blob = " ".join(labels).lower()
    for word in REJECTED:
        if word in blob:
            return "rejected", f"Facebook rejected the credentials ({word})"
    for word in CHALLENGE:
        if word in blob:
            return "challenge", f"a challenge is on screen ({word})"
    for word in GOOD:
        if word in blob:
            return "ok", "signed in"
    return "unknown", "the screen matched nothing known"


CLONE_PREFIX = "fbclone"


def ensure_clones(dev: Device, wanted: int, log=print) -> list[int]:
    """User ids that can each hold their own Facebook Lite session.

    Owner counts as the first slot, so `wanted` sessions need wanted-1 extra
    users. The device decides the ceiling - `pm get-max-users` is 4 on this
    image - and asking for more than it allows is answered with what exists
    rather than an exception: logging four accounts is better than logging
    none because the fifth would not fit.
    """
    # Android's default cap is 4 on this image, which is a build resource and
    # not a licence; root moves it by setting fw.max_users. Ask for room
    # first, then take whatever the device really allows.
    ceiling = dev.raise_user_limit(wanted)
    if wanted > ceiling:
        log(f"    device allows {ceiling} sessions in total "
            f"(pm get-max-users); {wanted} were asked for")
    wanted = max(1, min(wanted, ceiling))

    slots = [0]                                   # Owner is always slot one
    existing = {name: uid for uid, name in dev.users()
                if name.startswith(CLONE_PREFIX)}

    # Clones are only worth making if they can be SEEN. On LDPlayer they
    # cannot: the display is bound to user 0, so a clone switches into a black
    # screen and every login there reports "no username field" - which reads
    # as a Facebook problem and is an emulator one. Probe once with a real
    # clone and say so plainly rather than producing a column of false
    # failures.
    if wanted > 1:
        probe = existing.get(f"{CLONE_PREFIX}1")
        if probe is None:
            probe = dev.create_user(f"{CLONE_PREFIX}1")
            existing[f"{CLONE_PREFIX}1"] = probe
            dev.start_user(probe)
            dev.install_existing_for_user(PACKAGE, probe)
            dev.stop_user(probe)
        if not dev.clone_display_works(probe):
            log("    this emulator does not render secondary users: a clone "
                "switches into a black screen, so it cannot be driven.")
            log("    falling back to one session (Owner). For several live "
                "sessions use separate LDPlayer instances: "
                "ldconsole copy --name fb2 --from LDPlayer")
            return [0]
    for n in range(1, wanted):
        name = f"{CLONE_PREFIX}{n}"
        uid = existing.get(name)
        if uid is None:
            uid = dev.create_user(name)
            log(f"    created clone {name} (user {uid})")
        slots.append(uid)
    return slots


def login_one(dev: Device, username: str, password: str, log=print,
              user: int | None = None) -> tuple[str, str]:
    """Drive one login. Returns (verdict, detail)."""
    # Refuse BEFORE touching the app: a password adb cannot type exactly would
    # otherwise be half-entered and charged to the account as a failed login.
    if not dev.can_type(username):
        return "skipped", "the username holds characters adb cannot type"
    if not dev.can_type(password):
        return "skipped", "the password holds characters adb cannot type"

    # One clone awake at a time. Starting every clone up front left them all
    # resident and wedged a 6 GB device - `am get-current-user` timed out at
    # 60s and every account reported "no username field", which looked like a
    # Facebook problem and was an out-of-memory one. A stopped user keeps its
    # data, so the session survives being put back to sleep.
    #
    # The display also belongs to one user at a time, and every tap and dump
    # goes to whoever is in front: driving a clone without switching to it
    # types this account's password into whatever session IS in front.
    # Slot 0 is Owner: already running, already in front, and it cannot be
    # started or stopped - "Can't stop system user 0".
    if user:
        dev.start_user(user)
        dev.switch_user(user)
        time.sleep(10)          # the user's launcher has to come up first
    dev.stop(PACKAGE, user=user)
    dev.launch(PACKAGE, user=user)
    time.sleep(10)

    user_field = None
    for hint in USERNAME_HINTS:
        user_field = dev.wait_for(timeout=8, desc=hint, cls="android.widget.EditText")
        if user_field:
            break
    if user_field is None:
        # Fall back to shape: the first non-password text box on the form.
        boxes = [n for n in dev.screen()
                 if n.cls.endswith("EditText") and not n.password]
        user_field = boxes[0] if boxes else None
    if user_field is None:
        return "no form", "no username field on screen - dump it and re-read"

    dev.tap_node(user_field)
    dev.clear_field()
    dev.type_text(username)

    secret = find(dev.screen(), password=True)
    if not secret:
        return "no form", "no password field on screen"
    dev.tap_node(secret[0])
    dev.clear_field()
    dev.type_text(password)

    # Facebook Lite 529 ships NO resource ids at all, and puts every label in
    # content-desc with text left empty. It also nests a View inside the
    # Button carrying the same label, so a plain text match finds the inner
    # View: its centre happens to fall inside the Button, but that is luck,
    # not a contract. Prefer a real Button, on either field.
    nodes = dev.screen()
    button = None
    for hint in LOGIN_HINTS:
        hits = find(nodes, text=hint) + find(nodes, desc=hint)
        if hits:
            button = next((n for n in hits if n.cls.endswith("Button")), hits[0])
            break
    if button is None:
        log("    no Log In button found - submitting with the keyboard")
        dev.key("KEYCODE_ENTER")
    else:
        dev.tap_node(button)

    time.sleep(10)
    labels = [(n.text or n.desc) for n in dev.screen() if (n.text or n.desc)]
    verdict, detail = classify(labels)
    if verdict in ("rejected", "challenge"):
        return verdict, detail

    # Anything else needs the form test, not the labels: a working session
    # shows no text at all, so "unknown" and "ok" are indistinguishable by
    # reading the screen.
    log("    backing out of the setup screens (accepting nothing)")
    took = leave_onboarding(dev, user=user, log=log)

    # Hand the device back: Owner in front, this clone asleep. Its data - and
    # so its session - stays put.
    if user:                    # never Owner: it cannot be stopped
        dev.switch_user(0)
        dev.stop_user(user)

    if took:
        return "ok", "signed in"
    return "rejected", "still on the login form - the credentials did not take"


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="127.0.0.1:5555",
                    help="adb serial of the LDPlayer instance")
    ap.add_argument("--only", nargs="*", metavar="USERNAME", default=None)
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clear", action="store_true",
                    help="wipe Facebook Lite between accounts - DESTROYS the "
                         "session already on the device")
    ap.add_argument("--not-logged-in", action="store_true",
                    help="only the roster rows the sheet does not already "
                         "call LOGGED IN")
    ap.add_argument("--clones", type=int, default=1, metavar="N",
                    help="hold N sessions at once, one per Android user "
                         "(Owner counts as the first). The device caps this: "
                         "pm get-max-users is 4 on this image")
    args = ap.parse_args(argv)

    from src.storage import database as db

    # A Brave profile is a BROWSER concept: it names a directory the browser
    # fleet drives. Facebook Lite has neither, and needs only the username and
    # the password - so requiring a linked profile here excluded 993 of the
    # 1030 roster rows for no reason. Accounts are taken straight off the
    # roster; --not-logged-in narrows to the ones the sheet still calls out.
    accounts = list(db.list_accounts(include_disabled=False))
    if args.not_logged_in:
        accounts = [a for a in accounts
                    if (a.get("sheet_status") or "").strip().upper()
                    != "LOGGED IN"]
    if args.only:
        wanted = {u.strip().lower() for u in args.only if u.strip()}
        accounts = [a for a in accounts if a["username"].lower() in wanted]
    if args.count is not None:
        accounts = accounts[:args.count]
    if not accounts:
        print("No accounts to attempt.")
        return 0

    print(f"Accounts to attempt : {len(accounts)}")
    for a in accounts:
        print(f"   {a['username']}  ({a.get('facebook_name') or '-'})")
    if args.dry_run:
        print("\n--dry-run: the emulator was not touched.")
        return 0

    dev = Device(serial=args.serial)
    try:
        dev.connect()
    except Exception as e:  # noqa: BLE001
        print(f"Could not reach {args.serial}: {e}")
        print("Is the LDPlayer instance running, and is ADB enabled for it?")
        return 1

    if not dev.installed(PACKAGE):
        print(f"\n{PACKAGE} is not installed on {args.serial}.")
        print("Install it from the Play Store inside LDPlayer, or adb install "
              "an APK you trust. This script will not fetch one.")
        return 1

    slots: list[int | None] = [None]
    if args.clones > 1:
        print(f"\nProvisioning up to {args.clones} sessions...")
        slots = list(ensure_clones(dev, args.clones))
        for uid in slots:
            if uid:                      # Owner already holds the app
                # Share the app, then put the user straight back to sleep.
                # A stopped user resolves no components, so it is started
                # again for the few minutes its account is being driven - not
                # left running, which is what exhausted the device.
                dev.start_user(uid)
                dev.install_existing_for_user(PACKAGE, uid)
                dev.stop_user(uid)
        print(f"    sessions available: {len(slots)} (user ids {slots})")
        if len(slots) < len(accounts):
            print(f"    {len(accounts)} accounts for {len(slots)} sessions - "
                  f"later accounts reuse a slot, which needs --clear")

    results: dict[str, list[str]] = {}
    placed: list[tuple[str, int | None]] = []
    for i, a in enumerate(accounts, 1):
        username = a["username"]
        slot = slots[(i - 1) % len(slots)]
        password = db.password_for_username(username)
        creds = (username, password) if password else None
        if not creds:
            print(f"\n[{i}/{len(accounts)}] {username}: no password on the roster row")
            results.setdefault("no password", []).append(username)
            continue
        where = "Owner" if slot in (None, 0) else f"clone user {slot}"
        print(f"\n[{i}/{len(accounts)}] {username}  ->  {where}")
        if args.clear:
            print("    wiping Facebook Lite (destroys the session in this slot)")
            dev.clear_app_data(PACKAGE, user=slot)
        try:
            verdict, detail = login_one(dev, username, creds[1], log=print,
                                        user=slot)
        except Exception as e:  # noqa: BLE001 - one account must not end the run
            verdict, detail = "error", f"{type(e).__name__}: {e}"
        print(f"    {verdict}: {detail}")
        results.setdefault(verdict, []).append(username)
        if verdict == "ok":
            placed.append((username, slot))

    print("\n" + "=" * 60)
    for verdict, names in sorted(results.items()):
        print(f"  {verdict}: {len(names)}")
        for n in names:
            print(f"     {n}")
    if placed:
        print("\n  signed in, and which session each one lives in:")
        for username, slot in placed:
            where = "Owner" if slot in (None, 0) else f"clone user {slot}"
            print(f"     {username}  ->  {where}")
    print("\nThe roster was not modified: these are app sessions, and "
          "accounts.status means the BROWSER session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
