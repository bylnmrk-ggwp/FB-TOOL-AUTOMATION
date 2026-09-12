"""The Compose page's "My Groups" card: the saved list, and the fetch button.

ShareTab showed one line per group with the profiles that have it, loaded
from SQLite by "Load Saved" and refreshed by the two fetch buttons ("Fetch My
Groups (All Profiles)" and the one-profile picker). GET /api/groups is that
listbox as JSON - the page holds no group state of its own, so a phone that
opens Compose sees what the PC last fetched - and POST /api/groups/fetch is
both buttons, told apart by how many names the body carries.

Nothing here writes: the worker saves what it fetched through
db.save_profile_groups, and the outcome reaches every device on /ws as
fetch_groups_result / fetch_groups_bulk_result. No AppState field moves
either, so no state event is pushed from this module.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.storage import database as db

router = APIRouter(prefix="/api")

ACCEPTED = {"accepted": True}


class ProfileNamesBody(BaseModel):
    profile_names: list[str] | None = None


def _clean(names: list[str] | None) -> list[str] | None:
    """Drop blanks and repeats. An empty selection comes back as None: the
    worker reads `cmd["profile_names"] or cfg.list_profiles()`, so [] already
    means every profile, and None says that out loud on the queue."""
    if not names:
        return None
    seen: list[str] = []
    for n in names:
        n = str(n).strip()
        if n and n not in seen:
            seen.append(n)
    return seen or None


# ── The saved list ────────────────────────────────────


@router.get("/groups")
def groups() -> dict:
    """Every saved group once, with the profiles that have it.

    db.get_profile_groups() without a profile already merges the rows by URL;
    the keys are re-read here because this shape is the wire contract the
    frontend and the bulk-share body are written against, not the table's.
    """
    rows = []
    for g in db.get_profile_groups():
        name = str(g.get("name") or "").strip()
        url = str(g.get("url") or "").strip()
        if not name or not url:
            continue
        rows.append({"name": name, "url": url,
                     "profiles": [str(p) for p in (g.get("profiles") or [])]})
    rows.sort(key=lambda g: (g["name"].casefold(), g["url"]))
    return {"groups": rows}


# ── The fetch buttons ─────────────────────────────────


@router.post("/groups/fetch", status_code=202)
def fetch(body: ProfileNamesBody, request: Request) -> dict:
    """Refresh the saved list from Facebook.

    Exactly one name takes the single-profile command the Tk picker used: it
    launches that profile alone instead of sweeping every saved one, which is
    why the tab grew that row in the first place. Anything else is the bulk
    sweep, narrowed to the names when there are any.

    Refused while a run is on, like every fetch button that greyed itself out:
    the sweep opens a browser per profile and would fight whatever already
    holds one.
    """
    if request.app.state.appstate.run is not None:
        raise HTTPException(status_code=409, detail={"error": "a run is in progress"})
    names = _clean(body.profile_names)
    manager = request.app.state.manager
    if names is not None and len(names) == 1:
        manager.fetch_my_groups(names[0])
    else:
        manager.fetch_my_groups_bulk(profile_names=names)
    return ACCEPTED
