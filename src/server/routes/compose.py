"""The Compose page: ShareTab's buttons, one route each.

Same shape as routes/accounts.py - validate the body, refuse what the Tk
button would have greyed out (409), call the same DriverManager helper the
button called, answer 202. Outcomes never come back on the response; they
arrive on /ws as the worker's own result dicts.

The 409 here reads `AppState.run` and never writes it: the bridge owns that
field, and only the bridge knows when the last of a multi-group share has
landed. A route that opened the run itself would leave the button grey
forever the first time a command ended in a result the bridge closes the
run from but the route could not predict. Nothing else in this module
changes AppState, so none of these routes broadcasts one.

Two checks a desktop form never needed, because a phone posts JSON over the
network instead of typing into a widget: a post_url that is not a link, and
an image path that names a file the server never stored. post_to_timeline
hands its paths straight to Facebook's file chooser, so an unchecked path
would turn a crafted body into a read of any file on the PC.
"""
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from src.server import uploads

router = APIRouter(prefix="/api")

ACCEPTED = {"accepted": True}


# ── Bodies ────────────────────────────────────────────


class GroupRef(BaseModel):
    name: str


class BulkGroupRef(BaseModel):
    """One row of the saved-groups table: the name to search for, the URL
    it was found at, and the profiles that are members of it."""
    name: str
    url: str = ""
    profiles: list[str] = []


class ShareBody(BaseModel):
    post_url: str
    group_name: str
    comment_text: str | None = None
    reaction: str | None = None


class ShareTimelineBody(BaseModel):
    post_url: str
    comment_text: str | None = None
    reaction: str | None = None


class ShareGroupsBody(BaseModel):
    post_url: str
    groups: list[GroupRef] = []
    comment_text: str | None = None
    reaction: str | None = None


class ShareBulkBody(BaseModel):
    post_url: str
    groups: list[BulkGroupRef] = []
    comment_text: str | None = None
    reaction: str | None = None
    profile_names: list[str] | None = None


class JoinBody(BaseModel):
    urls: list[str] = []
    profile_names: list[str] | None = None


class PostTimelineBody(BaseModel):
    text: str = ""
    image_paths: list[str] | None = None


# ── Guards ────────────────────────────────────────────


def _idle(request: Request) -> None:
    """A run is driving Brave; every Compose button was grey until it
    ended, and a second command would fight it for the browser."""
    if request.app.state.appstate.run is not None:
        raise HTTPException(status_code=409, detail={"error": "a run is active"})


def _post_url(value: str) -> str:
    """What the Tk forms required before their button did anything: a
    link. The worker navigates to whatever it is given."""
    url = str(value or "").strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400,
                            detail={"error": "post_url must be a link"})
    return url


def _clean(names: list[str] | None) -> list[str] | None:
    """Drop blanks and repeats but keep None (= every profile) as None."""
    if names is None:
        return None
    seen: list[str] = []
    for n in names:
        n = str(n).strip()
        if n and n not in seen:
            seen.append(n)
    return seen


def _comment(text: str | None) -> str | None:
    stripped = (text or "").strip()
    return stripped or None


def _reaction(value: str | None) -> str | None:
    """ShareTab's reaction property: "none" and blank both mean no
    reaction, and the worker expects None for that."""
    val = (value or "").strip().lower()
    return None if val in ("", "none") else val


def _image_paths(paths: list[str] | None) -> list[str] | None:
    """Only files this server wrote. The path came back from a client, so
    it is checked against the upload folder rather than trusted - see the
    module docstring."""
    if not paths:
        return None
    root = Path(uploads.UPLOAD_DIR).resolve()
    out: list[str] = []
    for raw in paths:
        try:
            candidate = Path(str(raw)).resolve()
            ok = candidate.is_relative_to(root) and candidate.is_file()
        except (OSError, ValueError):
            # A path the filesystem will not even parse (a null byte, a
            # device name): refused like any other, never a 500.
            ok = False
        if not ok:
            raise HTTPException(
                status_code=400,
                detail={"error": "image_paths must be files uploaded to this server"})
        out.append(str(candidate))
    return out


# ── Share ─────────────────────────────────────────────


@router.post("/compose/share", status_code=202)
def share(body: ShareBody, request: Request) -> dict:
    _idle(request)
    url = _post_url(body.post_url)
    name = body.group_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail={"error": "group_name is required"})
    request.app.state.manager.share(url, name, comment_text=_comment(body.comment_text),
                                    reaction=_reaction(body.reaction))
    return ACCEPTED


@router.post("/compose/share-timeline", status_code=202)
def share_timeline(body: ShareTimelineBody, request: Request) -> dict:
    _idle(request)
    url = _post_url(body.post_url)
    request.app.state.manager.share_to_timeline(
        url, comment_text=_comment(body.comment_text), reaction=_reaction(body.reaction))
    return ACCEPTED


@router.post("/compose/share-groups", status_code=202)
def share_groups(body: ShareGroupsBody, request: Request) -> dict:
    _idle(request)
    url = _post_url(body.post_url)
    groups = [{"name": g.name.strip()} for g in body.groups if g.name.strip()]
    if not groups:
        raise HTTPException(status_code=400, detail={"error": "select a group first"})
    request.app.state.manager.share_to_groups(
        url, groups, comment_text=_comment(body.comment_text),
        reaction=_reaction(body.reaction))
    return ACCEPTED


@router.post("/compose/share-bulk", status_code=202)
def share_bulk(body: ShareBulkBody, request: Request) -> dict:
    """Every profile that is a member of the chosen groups, concurrently -
    the heaviest thing the page can start, and the 409 above is what keeps
    a second phone from starting it twice."""
    _idle(request)
    url = _post_url(body.post_url)
    groups = [{"name": g.name.strip(), "url": g.url, "profiles": list(g.profiles)}
              for g in body.groups if g.name.strip()]
    if not groups:
        raise HTTPException(status_code=400, detail={"error": "select a group first"})
    request.app.state.manager.share_to_groups_bulk(
        url, groups, comment_text=_comment(body.comment_text),
        reaction=_reaction(body.reaction), profile_names=_clean(body.profile_names))
    return ACCEPTED


# ── Groups and timeline posts ─────────────────────────


@router.post("/compose/join", status_code=202)
def join(body: JoinBody, request: Request) -> dict:
    _idle(request)
    # The Tk textarea dropped every line that was not a link and joined the
    # rest; a phone pastes the same list, newlines and all.
    urls = [u.strip() for u in body.urls if str(u).strip().startswith("http")]
    if not urls:
        raise HTTPException(status_code=400, detail={"error": "no group links given"})
    request.app.state.manager.join_group(urls, profile_names=_clean(body.profile_names))
    return ACCEPTED


@router.post("/compose/post-timeline", status_code=202)
def post_timeline(body: PostTimelineBody, request: Request) -> dict:
    _idle(request)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail={"error": "text is required"})
    request.app.state.manager.post_to_timeline(
        text, image_paths=_image_paths(body.image_paths))
    return ACCEPTED


# ── Uploads ───────────────────────────────────────────


@router.post("/uploads")
def upload(file: UploadFile = File(...)) -> dict:
    """Stage one image and answer with the path a later command names.

    Not a command: it starts nothing on the browser, so it is allowed while
    a run is on - the operator can pick photos on the phone and compose the
    post once the run ends.
    """
    # One byte past the cap is enough to refuse it; the rest never leaves
    # Starlette's spooled temp file.
    data = file.file.read(uploads.MAX_UPLOAD_BYTES + 1)
    try:
        path = uploads.save_upload(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)}) from e
    return {"path": path, "name": Path(path).name}
