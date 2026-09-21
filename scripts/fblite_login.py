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

# What the screen says once it is no longer the login form.
GOOD = ("what's on your mind", "home", "news feed", "marketplace",
        "notifications")
CHALLENGE = ("not a robot", "captcha", "confirm", "security check",
             "two-factor", "authentication", "verify", "checkpoint")
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


def login_one(dev: Device, username: str, password: str, log=print) -> tuple[str, str]:
    """Drive one login. Returns (verdict, detail)."""
    # Refuse BEFORE touching the app: a password adb cannot type exactly would
    # otherwise be half-entered and charged to the account as a failed login.
    if not dev.can_type(username):
        return "skipped", "the username holds characters adb cannot type"
    if not dev.can_type(password):
        return "skipped", "the password holds characters adb cannot type"

    dev.stop(PACKAGE)
    dev.launch(PACKAGE)
    time.sleep(6)

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

    nodes = dev.screen()
    button = None
    for hint in LOGIN_HINTS:
        hits = find(nodes, text=hint)
        if hits:
            button = hits[0]
            break
    if button is None:
        log("    no Log In button found - submitting with the keyboard")
        dev.key("KEYCODE_ENTER")
    else:
        dev.tap_node(button)

    time.sleep(10)
    labels = [(n.text or n.desc) for n in dev.screen() if (n.text or n.desc)]
    return classify(labels)


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
    args = ap.parse_args(argv)

    from src.storage import database as db

    accounts = [a for a in db.list_accounts(include_disabled=False)
                if a.get("linked_profile")]
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

    results: dict[str, list[str]] = {}
    for i, a in enumerate(accounts, 1):
        username = a["username"]
        creds = db.credentials_for_profile(a.get("linked_profile") or "")
        if not creds:
            print(f"\n[{i}/{len(accounts)}] {username}: no password on the roster row")
            results.setdefault("no password", []).append(username)
            continue
        print(f"\n[{i}/{len(accounts)}] {username}")
        if args.clear:
            print("    wiping Facebook Lite (destroys the session on the device)")
            dev.clear_app_data(PACKAGE)
        try:
            verdict, detail = login_one(dev, username, creds[1], log=print)
        except Exception as e:  # noqa: BLE001 - one account must not end the run
            verdict, detail = "error", f"{type(e).__name__}: {e}"
        print(f"    {verdict}: {detail}")
        results.setdefault(verdict, []).append(username)

    print("\n" + "=" * 60)
    for verdict, names in sorted(results.items()):
        print(f"  {verdict}: {len(names)}")
        for n in names:
            print(f"     {n}")
    print("\nThe roster was not modified: these are app sessions, and "
          "accounts.status means the BROWSER session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
