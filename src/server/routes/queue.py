"""The Queue page: the shared batch list, the Run button and the watch.

QueueTab's buttons, one route each. What changed on the way to the web is
where the list lives: the Tk tab handed its own items to run_queue, while
here they sit in QueueStore on app.state, so the phone that added three
items and the laptop that presses Run are looking at the same queue. Every
mutation pushes the state, because the other devices have no other way to
learn the list moved.

Run refuses (409) exactly where the Tk Run button greyed out - while a
batch, a login run or a login scan is on - under the app's command lock,
so two devices pressing Run in the same instant start one batch. The
outcome is never in the response; it arrives on /ws as batch_progress,
batch_item_result and batch_result.
"""
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.server.routes.system import push_state
from src.server.state import RunState

router = APIRouter(prefix="/api")

ACCEPTED = {"accepted": True}


# ── Bodies ────────────────────────────────────────────


class AddBody(BaseModel):
    """One quick-add form, for one or many profiles: the Tk tab added an
    item per displayed profile and so does this."""
    profile_names: list[str] = []
    action_type: str = "group"
    post_url: str | None = None
    group_name: str | None = None
    comment_text: str | None = None
    reaction: str | None = None
    text: str | None = None


class RemoveBody(BaseModel):
    id: str = ""


class WatchBody(BaseModel):
    url: str = ""
    minutes: float | None = None
    profile_names: list[str] | None = None


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


def _running(request: Request) -> bool:
    """Whether the Run button is grey. The same three flags decide the 409,
    so the button a device shows and the answer it gets agree."""
    state = request.app.state.appstate
    return (state.run is not None or state.login_run_active or state.scan_active)


def _queue_changed(request: Request) -> None:
    """One mutation, two announcements: the state event carries the run
    flags and the counts, and queue_changed tells a device holding the list
    to re-read it - the same pair accounts/link sends."""
    request.app.state.bridge.broadcast({"type": "queue_changed"})
    push_state(request)


# ── The list ──────────────────────────────────────────


@router.get("/queue")
def queue(request: Request) -> dict:
    return {"items": request.app.state.queue.items(),
            "running": _running(request)}


@router.post("/queue/add", status_code=202)
def add(body: AddBody, request: Request) -> dict:
    names = _clean(body.profile_names) or []
    if not names:
        raise HTTPException(status_code=400, detail={"error": "no profiles given"})
    store = request.app.state.queue
    fields = body.model_dump(exclude={"profile_names"})
    added = 0
    try:
        # The names are already blank-free and every other field is shared,
        # so the first item validates for all of them or for none: the
        # queue cannot end up half filled by a refused form.
        for name in names:
            store.add({**fields, "profile_name": name})
            added += 1
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)}) from e
    _queue_changed(request)
    return {**ACCEPTED, "added": added}


@router.post("/queue/remove")
def remove(body: RemoveBody, request: Request) -> dict:
    """By id, not by index: another device's remove shifts every index
    under the one this phone is looking at."""
    st = request.app.state
    item_id = body.id.strip()
    with st.cmd_lock:
        index = next((i for i, it in enumerate(st.queue.items())
                      if it.get("id") == item_id), None)
        if index is None or not st.queue.remove(index):
            raise HTTPException(status_code=404, detail={"error": "no such queue item"})
    _queue_changed(request)
    return {"ok": True}


@router.post("/queue/clear")
def clear(request: Request) -> dict:
    removed = request.app.state.queue.clear()
    _queue_changed(request)
    return {"ok": True, "removed": removed}


# ── Commands ──────────────────────────────────────────


@router.post("/queue/run", status_code=202)
def run(request: Request) -> dict:
    st = request.app.state
    with st.cmd_lock:
        # The 409 outranks the 400: with a run on, "the queue is empty"
        # would be a claim about the list rather than about the button.
        if _running(request):
            raise HTTPException(status_code=409, detail={"error": "a run is active"})
        items = st.queue.to_run()
        if not items:
            raise HTTPException(status_code=400, detail={"error": "the queue is empty"})
        st.manager.run_queue(items)
        # Opened here rather than at the first batch_progress so every
        # device greys its Run button the moment one of them presses it.
        st.appstate.run = RunState(kind="batch", total=len(items),
                                   message="Batch queued", started_at=time.time())
    push_state(request)
    return ACCEPTED


@router.post("/queue/watch", status_code=202)
def watch(body: WatchBody, request: Request) -> dict:
    """Opens a visible Brave window per active profile on the PC - the page
    says so before the tap, since the operator may be nowhere near it."""
    url = body.url.strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400,
                            detail={"error": "url must start with http"})
    minutes = body.minutes if body.minutes and body.minutes > 0 else None
    request.app.state.manager.watch_url(url, minutes=minutes,
                                        profile_names=_clean(body.profile_names))
    return ACCEPTED


@router.post("/queue/stop-watch", status_code=202)
def stop_watch(request: Request) -> dict:
    request.app.state.manager.stop_watch()
    return ACCEPTED
