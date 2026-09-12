"""Proof: src/server/uploads.py and the Compose routes.

Runs under verify.py with globals `failures`, `step` and `ROOT`. The
DriverManager is built but its thread is never started, so every command a
route accepts is a dict left on manager.cmd_queue for this proof to read;
nothing opens a browser and no image leaves this machine. uploads.UPLOAD_DIR
is pointed at a temp folder for the whole run and put back in the finally
block, so the operator's own ~/.autoshare/uploads is never written to.

The routes are mounted on a bare FastAPI() rather than create_app(): this
proof is about the compose router alone, and app.py is another task's file.
That also means no session cookie and no Origin check here - both are
app.py's middleware, proved by proofs/23_server.py.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("compose routes")  # noqa: F821
import queue as _q  # noqa: E402
import shutil as _sh  # noqa: E402
import tempfile as _tf  # noqa: E402
import warnings as _warnings  # noqa: E402
from pathlib import Path as _P  # noqa: E402

# starlette 1.6 warns that httpx (not httpx2) drives its TestClient; the
# proof works either way and the warning is not a finding.
_warnings.filterwarnings("ignore", message=".*httpx.*", module="starlette.*")
_warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.*")

from fastapi import FastAPI as _FastAPI  # noqa: E402
from fastapi.testclient import TestClient as _TestClient  # noqa: E402

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.server import uploads as _uploads  # noqa: E402
from src.server.routes import compose as _compose  # noqa: E402
from src.server.state import AppState as _AppState  # noqa: E402
from src.server.state import RunState as _RunState  # noqa: E402

_URL = "https://www.facebook.com/verify/posts/1"
_SAFE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")


def _fail(msg):
    failures.append(f"compose: {msg}")  # noqa: F821


def _drain_cmds(manager):
    out = []
    while True:
        try:
            out.append(manager.cmd_queue.get_nowait())
        except _q.Empty:
            return out


def _expect_cmd(manager, resp, status, ctype, what):
    """One accepted route -> one command of the expected type on the queue."""
    cmds = _drain_cmds(manager)
    if resp.status_code != status:
        _fail(f"{what}: status {resp.status_code} body {resp.text[:120]}")
    if status == 202 and resp.json() != {"accepted": True}:
        _fail(f"{what}: body {resp.text[:120]}")
    if [c.get("type") for c in cmds] != [ctype]:
        _fail(f"{what}: queued {[c.get('type') for c in cmds]}, expected [{ctype!r}]")
    return cmds[0] if cmds else {}


def _expect_refused(manager, resp, status, what):
    """A refused route answers `status` and queues nothing at all."""
    if resp.status_code != status:
        _fail(f"{what}: status {resp.status_code} body {resp.text[:120]}")
    cmds = _drain_cmds(manager)
    if cmds:
        _fail(f"{what}: refused but queued {[c.get('type') for c in cmds]}")


_tmp = _P(_tf.mkdtemp(prefix="verify_compose_"))
_real_upload_dir = _uploads.UPLOAD_DIR
_m = _DM()
_m.log = lambda _msg: None      # the driver logs non-ASCII; keep stdout clean

try:
    _dir = _tmp / "uploads"
    _uploads.UPLOAD_DIR = _dir

    # -- save_upload: the name is rebuilt, never trusted ---------------
    _stored = _P(_uploads.save_upload("../../evil.png", b"png-bytes"))
    if not _stored.is_file():
        _fail(f"save_upload wrote nothing at {_stored}")
    elif _stored.read_bytes() != b"png-bytes":
        _fail("save_upload wrote the wrong bytes")
    if not _stored.is_absolute():
        _fail(f"save_upload returned a relative path: {_stored}")
    if not _stored.resolve().is_relative_to(_dir.resolve()):
        _fail(f"save_upload escaped the upload folder: {_stored}")
    if _stored.name != "evil.png":
        _fail(f"save_upload stored '../../evil.png' as {_stored.name!r}")
    if ".." in _stored.parts:
        _fail(f"save_upload kept a '..' segment: {_stored}")

    # A second file of the same name is kept, not overwritten.
    _second = _P(_uploads.save_upload("evil.png", b"other-bytes"))
    if _second == _stored:
        _fail("save_upload overwrote an existing file")
    elif not _second.is_file() or _stored.read_bytes() != b"png-bytes":
        _fail("a colliding upload clobbered the first file")

    # Anything a phone can put in a filename comes out of the allowed set.
    _odd = _P(_uploads.save_upload("my photo (1);rm -rf.JPG", b"jpg"))
    if set(_odd.name) - _SAFE:
        _fail(f"stored name has unsafe characters: {_odd.name!r}")
    if _odd.suffix != ".jpg":
        _fail(f"stored suffix={_odd.suffix!r}, expected '.jpg'")

    _before = sorted(p.name for p in _dir.rglob("*") if p.is_file())
    for _bad, _why in ((("payload.exe", b"MZ"), "an .exe"),
                       (("script.png.exe", b"MZ"), "a double extension"),
                       (("noext", b"x"), "no extension"),
                       (("big.png", bytes(_uploads.MAX_UPLOAD_BYTES + 1)), "an oversize file")):
        try:
            _uploads.save_upload(*_bad)
            _fail(f"save_upload accepted {_why}")
        except ValueError:
            pass
    _after = sorted(p.name for p in _dir.rglob("*") if p.is_file())
    if _after != _before:
        _fail(f"a refused upload still wrote a file: {set(_after) - set(_before)}")

    # -- the routes, on a bare app ------------------------------------
    _app = _FastAPI()
    _app.include_router(_compose.router)
    _state = _AppState()
    _app.state.manager = _m
    _app.state.appstate = _state

    def _walk(routes):
        # FastAPI 0.141 keeps an included router as one nested entry that
        # points back at the router; older releases flattened the routes.
        for r in routes:
            inner = getattr(getattr(r, "original_router", None), "routes", None)
            if inner is not None:
                yield from _walk(inner)
            elif hasattr(r, "path"):
                for m in (getattr(r, "methods", None) or set()):
                    yield (m, r.path)

    _routes = set(_walk(_app.routes))
    for _want in [("POST", "/api/compose/share"),
                  ("POST", "/api/compose/share-timeline"),
                  ("POST", "/api/compose/share-groups"),
                  ("POST", "/api/compose/share-bulk"),
                  ("POST", "/api/compose/join"),
                  ("POST", "/api/compose/post-timeline"),
                  ("POST", "/api/uploads")]:
        if _want not in _routes:
            _fail(f"route missing: {_want}")

    with _TestClient(_app) as _c:
        _cmd = _expect_cmd(_m, _c.post("/api/compose/share",
                                       json={"post_url": _URL, "group_name": " G ",
                                             "comment_text": "hi", "reaction": "like"}),
                           202, "share", "/api/compose/share")
        if (_cmd.get("post_url"), _cmd.get("group_name"), _cmd.get("comment_text"),
                _cmd.get("reaction")) != (_URL, "G", "hi", "like"):
            _fail(f"share cmd={_cmd}")

        _cmd = _expect_cmd(_m, _c.post("/api/compose/share-timeline",
                                       json={"post_url": _URL, "reaction": "love"}),
                           202, "share_to_timeline", "/api/compose/share-timeline")
        if _cmd.get("post_url") != _URL or _cmd.get("reaction") != "love":
            _fail(f"share_to_timeline cmd={_cmd}")

        _cmd = _expect_cmd(_m, _c.post("/api/compose/share-groups",
                                       json={"post_url": _URL,
                                             "groups": [{"name": "A"}, {"name": "B"}],
                                             "comment_text": "c"}),
                           202, "share_to_groups", "/api/compose/share-groups")
        if [g.get("name") for g in (_cmd.get("groups") or [])] != ["A", "B"]:
            _fail(f"share_to_groups groups={_cmd.get('groups')}")

        _cmd = _expect_cmd(_m, _c.post("/api/compose/share-bulk",
                                       json={"post_url": _URL,
                                             "groups": [{"name": "A", "url": "https://g/1",
                                                         "profiles": ["P1", "P2"]}],
                                             "profile_names": ["P1"]}),
                           202, "share_to_groups_bulk", "/api/compose/share-bulk")
        _g = (_cmd.get("groups") or [{}])[0]
        if (_g.get("name"), _g.get("url"), _g.get("profiles")) != ("A", "https://g/1",
                                                                  ["P1", "P2"]):
            _fail(f"share_to_groups_bulk group={_g}")
        if _cmd.get("profile_names") != ["P1"]:
            _fail(f"share_to_groups_bulk profile_names={_cmd.get('profile_names')}")

        # The Tk form dropped lines that are not links and joined the rest.
        _cmd = _expect_cmd(_m, _c.post("/api/compose/join",
                                       json={"urls": ["https://g/1", "not a link",
                                                      "https://g/2"],
                                             "profile_names": ["P1"]}),
                           202, "join_group_bulk", "/api/compose/join")
        if _cmd.get("group_urls") != ["https://g/1", "https://g/2"]:
            _fail(f"join group_urls={_cmd.get('group_urls')}")
        if _cmd.get("profile_names") != ["P1"]:
            _fail(f"join profile_names={_cmd.get('profile_names')}")

        # -- uploads, then a post that names the stored file -----------
        _r = _c.post("/api/uploads",
                     files={"file": ("shot.png", b"real-bytes", "image/png")})
        _body = _r.json() if _r.status_code == 200 else {}
        _path = _body.get("path", "")
        if _r.status_code != 200 or not _path:
            _fail(f"/api/uploads: {_r.status_code} {_r.text[:120]}")
        elif not _P(_path).resolve().is_relative_to(_dir.resolve()):
            _fail(f"/api/uploads stored outside the upload folder: {_path}")
        elif _P(_path).read_bytes() != b"real-bytes":
            _fail("/api/uploads stored the wrong bytes")
        elif _body.get("name") != _P(_path).name:
            _fail(f"/api/uploads name={_body.get('name')!r} path={_path}")
        _expect_refused(_m, _c.post("/api/uploads",
                                    files={"file": ("payload.exe", b"MZ",
                                                    "application/octet-stream")}),
                        400, "/api/uploads with an .exe")
        _expect_refused(_m, _c.post("/api/uploads",
                                    files={"file": ("big.png",
                                                    bytes(_uploads.MAX_UPLOAD_BYTES + 1),
                                                    "image/png")}),
                        400, "/api/uploads oversize")

        _cmd = _expect_cmd(_m, _c.post("/api/compose/post-timeline",
                                       json={"text": "hello", "image_paths": [_path]}),
                           202, "post_to_timeline", "/api/compose/post-timeline")
        if _cmd.get("text") != "hello" or _cmd.get("image_paths") != [_path]:
            _fail(f"post_to_timeline cmd={_cmd}")
        _expect_cmd(_m, _c.post("/api/compose/post-timeline", json={"text": "no images"}),
                    202, "post_to_timeline", "post-timeline without images")

        # -- refusals: 400 ---------------------------------------------
        for _path_, _body_, _what in (
                ("/api/compose/share", {"post_url": "javascript:alert(1)",
                                        "group_name": "G"}, "share with a bad post_url"),
                ("/api/compose/share", {"post_url": _URL, "group_name": "  "},
                 "share with a blank group_name"),
                ("/api/compose/share-timeline", {"post_url": "fb.com/x"},
                 "share-timeline with a bad post_url"),
                ("/api/compose/share-groups", {"post_url": _URL, "groups": []},
                 "share-groups with no groups"),
                ("/api/compose/share-bulk", {"post_url": "nope", "groups": []},
                 "share-bulk with a bad post_url"),
                ("/api/compose/join", {"urls": ["nope", ""]}, "join with no links"),
                ("/api/compose/post-timeline", {"text": "   "},
                 "post-timeline with empty text")):
            _expect_refused(_m, _c.post(_path_, json=_body_), 400, _what)

        # A crafted body must not turn the file chooser into a file reader.
        for _outside in (str(ROOT / "verify.py"),  # noqa: F821
                         str(_dir.resolve() / ".." / "outside.png"),
                         "C:/Windows/win.ini",
                         "shot.png\x00.txt"):
            _expect_refused(_m, _c.post("/api/compose/post-timeline",
                                        json={"text": "hi", "image_paths": [_outside]}),
                            400, f"post-timeline with {_outside[:40]} outside uploads")

        # -- refusals: 409 while a run drives Brave --------------------
        _state.run = _RunState(kind="share", current=1, total=3, message="sharing")
        for _path_, _body_ in (("/api/compose/share",
                                {"post_url": _URL, "group_name": "G"}),
                               ("/api/compose/share-timeline", {"post_url": _URL}),
                               ("/api/compose/share-groups",
                                {"post_url": _URL, "groups": [{"name": "A"}]}),
                               ("/api/compose/share-bulk",
                                {"post_url": _URL, "groups": [{"name": "A"}]}),
                               ("/api/compose/join", {"urls": ["https://g/1"]}),
                               ("/api/compose/post-timeline", {"text": "hi"})):
            _expect_refused(_m, _c.post(_path_, json=_body_), 409, f"{_path_} during a run")
        # Staging an image is not a command: the phone may upload while a
        # run is on and compose once it ends.
        _r = _c.post("/api/uploads", files={"file": ("during.png", b"x", "image/png")})
        if _r.status_code != 200:
            _fail(f"/api/uploads during a run: {_r.status_code} {_r.text[:120]}")
        _state.run = None
finally:
    _uploads.UPLOAD_DIR = _real_upload_dir
    _sh.rmtree(_tmp, ignore_errors=True)

print("ok" if not [f for f in failures if f.startswith("compose:")]  # noqa: F821
      else "FAILED")
