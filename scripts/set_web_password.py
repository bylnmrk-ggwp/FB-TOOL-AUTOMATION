"""Set (or check) the web app's operator password.

The web server (server.py) refuses to start until a bcrypt hash exists under
the `web_password_hash` key of ~/.autoshare/config.json, and this script is
the only thing that writes one. The password itself is never stored or
echoed; getpass hides it while typing.

Usage:
    python scripts/set_web_password.py           # prompts twice, stores the hash
    python scripts/set_web_password.py --check   # exit 0 when a hash exists, 1 when not
"""
import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.server import auth  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set the password the web app's login page accepts.")
    parser.add_argument("--check", action="store_true",
                        help="report whether a hash exists (exit 0) or not (exit 1); never prompts")
    args = parser.parse_args(argv)

    if args.check:
        if auth.stored_hash():
            print(f"web_password_hash is set in {cfg.CONFIG_FILE}")
            return 0
        print(f"web_password_hash is NOT set in {cfg.CONFIG_FILE} "
              "- run this script without --check")
        return 1

    if auth.stored_hash():
        print(f"A password is already set in {cfg.CONFIG_FILE}; it will be replaced.")
    first = getpass.getpass(f"New web password (at least {auth.MIN_PASSWORD_CHARS} characters): ")
    if len(first) < auth.MIN_PASSWORD_CHARS:
        print(f"Refused: at least {auth.MIN_PASSWORD_CHARS} characters. Nothing changed.",
              file=sys.stderr)
        return 1
    if len(first.encode("utf-8")) > auth.BCRYPT_MAX_BYTES:
        print(f"Refused: bcrypt accepts at most {auth.BCRYPT_MAX_BYTES} bytes. Nothing changed.",
              file=sys.stderr)
        return 1
    second = getpass.getpass("Repeat it: ")
    if first != second:
        print("Refused: the two entries differ. Nothing changed.", file=sys.stderr)
        return 1
    auth.store_password(first)
    print(f"Stored a bcrypt hash under web_password_hash in {cfg.CONFIG_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
