"""Pure reads behind /api/state and /api/accounts.

Nothing here touches the manager, the sheet or a browser. These are the
database and config reads the Tk tabs made piecemeal (ProfilesTab's roster
count and "logged in only" filter, the dashboard's pending count), gathered
in one place so a route, the event bridge and a proof all get the same
numbers without a widget or a worker thread. Every value comes back
JSON-safe.
"""
from datetime import datetime

from src.storage import config_manager as cfg
from src.storage import database as db


def counts() -> dict:
    """The dashboard numbers: how many accounts, and where each stands.

    logged_in and active are the same figure - Brave profiles whose linked
    account has status 'ok' - under two keys because the stat card calls it
    "Logged in" and the status bar calls it "Active".
    """
    total, _linked = db.count_accounts()
    logged_in = len(db.logged_in_profiles())
    pending, pending_unlinked = db.count_pending()
    return {
        "total": total,
        "logged_in": logged_in,
        "pending": pending,
        "pending_unlinked": pending_unlinked,
        "disabled": db.count_disabled(),
        "profiles": len(cfg.list_profiles()),
        "active": logged_in,
    }


def _restricted(profile_name: str) -> bool:
    """Whether Facebook is currently refusing this profile's shares."""
    return bool(profile_name) and db.share_restriction(profile_name) is not None


def accounts_rows() -> list[dict]:
    """The Accounts table: every roster account, then every saved Brave
    profile no account links to, so the page lists the same set ProfilesTab
    lists. A username of None marks the profile-only rows.

    `number` is left out on purpose: the phone number has no use on the page
    and would otherwise travel with every refresh.
    """
    rows = []
    linked = set()
    for acct in db.list_accounts():
        profile = acct.get("linked_profile") or ""
        if profile:
            linked.add(profile)
        rows.append({
            "sheet_no": acct.get("sheet_no"),
            "facebook_name": acct.get("facebook_name") or "",
            "username": acct.get("username"),
            "gmail": acct.get("gmail") or "",
            "linked_profile": profile,
            "status": acct.get("status") or "",
            "status_reason": acct.get("status_reason") or "",
            "sheet_status": acct.get("sheet_status") or "",
            "logged_in": acct.get("status") == "ok",
            "restricted": _restricted(profile),
        })
    for name in cfg.list_profiles():
        if name in linked:
            continue
        rows.append({
            "sheet_no": None,
            "facebook_name": "",
            "username": None,
            "gmail": "",
            "linked_profile": name,
            "status": "",
            "status_reason": "",
            "sheet_status": "",
            "logged_in": False,
            "restricted": _restricted(name),
        })
    return rows


def pending_usernames() -> list[str]:
    """The accounts "Log in pending" targets: never logged in from this
    tool, not disabled, and linked to a Brave profile - a login needs a
    profile to run in, so the unlinked ones are counted but not sent."""
    return [a["username"] for a in db.pending_accounts()
            if a.get("linked_profile")]


def summary_line(ok: int, failed: int, when: datetime | None = None) -> str:
    """The one-line outcome of a batch, as the dashboard's Run card shows
    it: "3 ok · 1 failed · 20:11". The separator is U+00B7 on purpose - it
    reads as a divider in a sans face where a hyphen reads as a minus."""
    when = when or datetime.now()
    return f"{ok} ok · {failed} failed · {when:%H:%M}"
