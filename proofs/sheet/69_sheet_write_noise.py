"""A run that cannot reach the sheet says so once, not once per account.

A DNS failure made every status push print urllib3's three nested
exceptions - "HTTPSConnectionPool(host='oauth2.googleapis.com', port=443):
Max retries exceeded with url: /token (Caused by NameResolutionError(..." -
under its own account name. One offline PC produced hundreds of identical
lines, and the real per-account results were buried between them.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("sheet write noise")  # noqa: F821

from src.core.driver_manager import DriverManager, sheet_reason  # noqa: E402
from src.storage import database as db  # noqa: E402

DNS = Exception("HTTPSConnectionPool(host='oauth2.googleapis.com', port=443): "
                "Max retries exceeded with url: /token (Caused by "
                "NameResolutionError(\"Failed to resolve 'oauth2.googleapis.com' "
                "([Errno 11001] getaddrinfo failed)\"))")

said = sheet_reason(DNS)
if "offline" not in said or len(said) > 60:
    failures.append(f"sheet write noise: the reason is still a dump: {said!r}")  # noqa: F821
kept = sheet_reason(ValueError("tab 'Sheet1' not found"))
if "Sheet1" not in kept:
    failures.append(f"sheet write noise: a real error lost its words: {kept!r}")  # noqa: F821

# Pushing for three accounts while offline logs the reason once.
USERS = ["verify_noise1@example.com", "verify_noise2@example.com",
         "verify_noise3@example.com"]
_real_account = db.account_for_profile
try:
    db.account_for_profile = lambda name: {"username": name}
    import src.storage.sheet_status as sheet_status
    _real_push = sheet_status.push_account_status

    def _offline(username):
        raise DNS

    sheet_status.push_account_status = _offline

    m = DriverManager()
    lines = []
    m.log = lines.append
    for user in USERS:
        asyncio.run(m._push_sheet_status(user))

    warnings = [line for line in lines if "sheet not updated" in line]
    if len(warnings) != 1:
        failures.append(f"sheet write noise: {len(warnings)} warning(s) for three "  # noqa: F821
                        f"accounts, expected 1: {warnings}")
    if warnings and ("HTTPSConnectionPool" in warnings[0] or len(warnings[0]) > 120):
        failures.append(f"sheet write noise: the warning is still a dump: "  # noqa: F821
                        f"{warnings[0][:80]!r}")
    if warnings and "recorded locally" not in warnings[0]:
        failures.append("sheet write noise: the warning does not say the verdicts "  # noqa: F821
                        "were still recorded")

    # A sheet that comes back reports its next failure again.
    sheet_status.push_account_status = lambda username: "LOGGED IN"
    asyncio.run(m._push_sheet_status(USERS[0]))
    sheet_status.push_account_status = _offline
    lines.clear()
    asyncio.run(m._push_sheet_status(USERS[1]))
    if not [line for line in lines if "sheet not updated" in line]:
        failures.append("sheet write noise: after a successful write, the next "  # noqa: F821
                        "failure is never reported")
finally:
    db.account_for_profile = _real_account
    import src.storage.sheet_status as sheet_status
    sheet_status.push_account_status = _real_push

print("FAILED" if [f for f in failures if "sheet write noise" in f] else "ok")  # noqa: F821
