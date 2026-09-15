"""EventBridge: MainWindow._poll_queue without the window.

The desktop app learns what the worker did by polling manager.poll_result()
every 100 ms on the Tk thread and switching on each result's "type" in
MainWindow._handle_result. Most of that method paints widgets; the rest -
the log lines, the batch summary, the "a run is on" state the buttons
expressed, answering the worker's image prompt, applying results to the
database - is what a phone needs as well. This thread does exactly that
remaining part, branch for branch (the _on_<rtype> methods below follow
_handle_result's order so the two can be read side by side), and hands every
result on to the WebSocket subscribers verbatim so the frontend switches on
the same rtype strings. DriverManager's contract is untouched: this reads
result dicts and calls the helpers the window already called.

Threads: results are handled on this thread; routes call
answer_input() from the event loop; the fan-out delivers into asyncio queues
through the loop's call_soon_threadsafe. One re-entrant lock guards every
AppState mutation so a route's answer and the timeout's cancel never race.
"""
import asyncio
import hashlib
import threading
import time
import traceback
from collections import deque
from pathlib import Path

from src.server import data
from src.server.logbuf import LogRing
from src.server.state import LAST_RUN_SUMMARY_KEY, AppState, RunState
from src.storage import config_manager as cfg

# Every rtype MainWindow._handle_result switches on (24, in its order), plus
# the two the login run emits that the Tk window never grew a branch for.
# proofs/24_parity.py diffs this against the window's source.
HANDLED_RTYPES: tuple[str, ...] = (
    "login_result",
    "share_result",
    "share_bulk_result",
    "share_bulk_profile_progress",
    "share_bulk_profile_result",
    "share_progress",
    "join_group_result",
    "join_group_progress",
    "join_group_profile_progress",
    "join_group_item_result",
    "join_group_bulk_result",
    "fetch_groups_bulk_result",
    "fetch_groups_profile_progress",
    "batch_progress",
    "batch_item_result",
    "login_scan_progress",
    "login_scan_result",
    "auto_setup_result",
    "auto_setup_images_preview",
    "auto_setup_all_progress",
    "auto_setup_all_result",
    "batch_result",
    "fetch_groups_result",
    "logout_result",
    "login_accounts_progress",
    "login_accounts_result",
)

# How long an image prompt waits for a device to answer before the bridge
# answers "cancel" itself. The worker blocks on that answer, so an unanswered
# prompt would otherwise hold the whole queue until someone opened the app.
INPUT_TIMEOUT_S = 600

# manager.get_memory_stats() is cached for a second inside the manager and
# walks every process; the Tk monitor asked about this often, no more.
SYSTEM_EVERY_S = 2.0

# rtype prefix -> RunState.kind. Ordered: "login_scan" and "login_accounts"
# must be tried before anything shorter could match them.
_RUN_KINDS = (
    ("batch", "batch"),
    ("login_scan", "scan"),
    ("login_accounts", "login"),
    ("auto_setup_all", "auto_setup"),
    ("join_group", "join"),
    ("share", "share"),
    ("fetch_groups", "fetch"),
)

_RULE = "=" * 50
_CHECK, _CROSS, _WARN = "✓", "✗", "⚠"


def _run_kind(rtype: str) -> str:
    for prefix, kind in _RUN_KINDS:
        if rtype.startswith(prefix):
            return kind
    return rtype[:-len("_progress")] if rtype.endswith("_progress") else rtype


class EventBridge(threading.Thread):
    def __init__(self, manager, state: AppState, logring: LogRing,
                 poll_ms: int = 100):
        super().__init__(name="EventBridge", daemon=True)
        self.manager = manager
        self.state = state
        self.logring = logring
        self._poll_s = max(poll_ms, 1) / 1000.0
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        # The shared batch list, handed over by create_app. None until then,
        # and in a proof that builds a bridge on its own.
        self.queue = None
        # Fan-out: the loop the WebSocket handlers live on, and their queues.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subs: set = set()
        self._subs_lock = threading.Lock()
        # The last events broadcast, for proofs and for a handler that wants
        # to know what a subscriber missed. Not a replay buffer.
        self.recent: deque = deque(maxlen=200)
        # image id -> local path, valid only while a prompt is open: the
        # image route serves nothing outside this dict.
        self._images: dict[str, str] = {}
        # Items reported ok since the batch began; batch_result carries only
        # the total, so the summary is counted here.
        self._batch_ok = 0
        self._system_at = 0.0
        self._system_error = None

    # ── Fan-out (thread-safe) ─────────────────────────────

    def attach_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop

    def attach_queue(self, store) -> None:
        """The QueueStore create_app owns. The bridge only ever empties it,
        at the end of a batch; every other change comes from a route."""
        self.queue = store

    def subscribe(self) -> asyncio.Queue:
        """A queue this bridge will feed. Call on the attached loop."""
        q: asyncio.Queue = asyncio.Queue()
        with self._subs_lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._subs_lock:
            self._subs.discard(q)

    def broadcast(self, event: dict) -> None:
        """Hand one event to every subscriber. Safe from any thread, and a
        no-op for the queues when no loop is attached (proofs, startup)."""
        self.recent.append(event)
        loop = self._loop
        if loop is None:
            return
        with self._subs_lock:
            subs = list(self._subs)
        for q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:
                # The loop is closed: the server is shutting down and the
                # subscriber is already gone.
                pass

    # ── Log and state helpers ─────────────────────────────

    def _log(self, message: str) -> None:
        """One line to the ring and the file, then to every device - the
        same path server.py gives manager.log."""
        entry = self.logring.write(message)
        if isinstance(entry, dict):
            self.broadcast({"type": "log", **entry})

    def _state_event(self) -> dict:
        return {"type": "state", **self.state.to_dict(), "counts": data.counts()}

    def _broadcast_state(self) -> None:
        self.broadcast(self._state_event())

    def _set_run(self, rtype: str, result: dict) -> None:
        """A progress event with current/total is the run in progress. The
        start time survives from one progress event to the next of the same
        kind, since a run announces itself only through its first one."""
        kind = _run_kind(rtype)
        run = self.state.run
        started = (run.started_at if run is not None and run.kind == kind
                   and run.started_at else time.time())
        self.state.run = RunState(
            kind=kind,
            current=result.get("current", 0) or 0,
            total=result.get("total", 0) or 0,
            message=str(result.get("message", "") or ""),
            profile_name=str(result.get("profile_name", "") or ""),
            started_at=started,
        )

    # ── Results (bridge thread; proofs call these directly) ───────────

    def handle_result(self, result: dict) -> None:
        """Apply one worker result the way _handle_result did, then forward
        it verbatim and, when any AppState field moved, the state after it."""
        with self._lock:
            before = self.state.to_dict()
            try:
                self._apply(result)
            finally:
                # Forwarded even when a branch above raised: the frontend
                # switches on the same result and must not lose it to a
                # bridge bug. The exception still reaches run()'s log.
                self.broadcast(dict(result))
            if self.state.to_dict() != before:
                self._broadcast_state()

    def _apply(self, result: dict) -> None:
        rtype = result.get("type")
        ok = result.get("ok", False)
        if not isinstance(rtype, str):
            self._on_other(result)
            return
        if rtype.endswith("_progress") and "current" in result and "total" in result:
            self._set_run(rtype, result)
        handler = getattr(self, f"_on_{rtype}", None) if rtype in HANDLED_RTYPES else None
        if handler is not None:
            handler(result, ok)
        else:
            self._on_other(result)
        text = self._failure_text(rtype, result)
        if text:
            self.broadcast({"type": "error", "text": text})

    @staticmethod
    def _failure_text(rtype: str, result: dict) -> str | None:
        """The toast text for a *_result that carries ok False and an error
        (spec section 9). Per-item and per-profile results are excluded: a
        bulk join or share reports every refused item that way and its own
        *_bulk_result sums them up; likewise a share_result inside a
        multi-group share (total > 1), which the window only logged."""
        if not rtype.endswith("_result"):
            return None
        if rtype.endswith("_item_result") or rtype.endswith("_profile_result"):
            return None
        if rtype == "share_result" and result.get("total", 0) > 1:
            return None
        if result.get("ok") is not False:
            return None
        err = result.get("error")
        return str(err) if err else None

    def _on_other(self, result: dict) -> None:
        """Results the window had no branch for. DriverManager._async_run
        reports a handler that raised as {"type": <command>, "success":
        False, "message": ...}; the Tk buttons stayed disabled after one of
        those until a restart, and on a server the same stuck flag would
        answer 409 to every later request, so the flags that command owned
        are released here."""
        if result.get("success") is False:
            ctype = result.get("type")
            if ctype == "login_accounts":
                self.state.login_run_active = False
            elif ctype == "check_login_status":
                self.state.scan_active = False
            self.state.run = None
        text = result.get("message") or result.get("error")
        if text:
            self._log(str(text))

    def _on_login_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        if ok:
            profile_name = r.get("profile_name", "")
            if r.get("needs_login", False):
                self._log(f"Profile '{profile_name}' — not logged in")
            else:
                self._log(f"Profile '{profile_name}' ready")
        else:
            self._log(f"Profile error: {r.get('error', 'Unknown error')}")

    def _on_share_result(self, r: dict, ok: bool) -> None:
        # Inside a multi-group share each group answers with one of these;
        # the window only logged those and left the buttons alone.
        is_bulk_item = r.get("total", 0) > 1
        if ok:
            self._log(r.get("message", "Shared successfully"))
        else:
            self._log(f"Share failed: {r.get('error', r.get('message', 'Unknown error'))}")
        if not is_bulk_item:
            self.state.run = None

    def _on_share_bulk_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        self._log(_RULE)
        self._log(r.get("message", "Done"))
        self._log(_RULE)

    def _on_share_bulk_profile_progress(self, r: dict, ok: bool) -> None:
        self._log(f"{'OK' if ok else 'FAIL'} {r.get('message', '')}")

    def _on_share_bulk_profile_result(self, r: dict, ok: bool) -> None:
        self._log(f"{'OK' if ok else 'FAIL'} {r.get('profile_name', '')}: "
                  f"{r.get('message', '')}")

    def _on_share_progress(self, r: dict, ok: bool) -> None:
        self._log(r.get("message", ""))

    def _on_join_group_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        if ok:
            self._log(r.get("message", "Joined successfully"))
        else:
            self._log(f"Join group failed: "
                      f"{r.get('error', r.get('message', 'Unknown error'))}")

    def _on_join_group_progress(self, r: dict, ok: bool) -> None:
        self._log(r.get("message", ""))

    def _on_join_group_profile_progress(self, r: dict, ok: bool) -> None:
        self._log(f"{_CHECK if ok else _CROSS} {r.get('message', '')}")

    def _on_join_group_item_result(self, r: dict, ok: bool) -> None:
        msg = r.get("message", r.get("error", ""))
        self._log(f"{_CHECK if ok else _CROSS} {r.get('profile_name', '')} "
                  f"[{r.get('current', 0)}/{r.get('total', 1)}] "
                  f"{r.get('url', '')}: {msg}")

    def _on_join_group_bulk_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        self._log(_RULE)
        self._log(r.get("message", "Done"))
        for pr in r.get("profile_results", []):
            pname = pr.get("profile_name", "?")
            if pr.get("ok"):
                parts = []
                if pr.get("success", 0):
                    parts.append(f"{pr['success']} joined")
                if pr.get("failed", 0):
                    parts.append(f"{pr['failed']} failed")
                if pr.get("skipped", 0):
                    parts.append(f"{pr['skipped']} skipped")
                self._log(f"  {pname}: {', '.join(parts) if parts else 'done'}")
            else:
                self._log(f"  {pname}: {pr.get('error', 'skipped')}")
        self._log(_RULE)

    def _on_fetch_groups_bulk_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        if ok:
            groups = r.get("groups", [])
            total = r.get("total_groups", len(groups))
            self._log(_RULE)
            self._log(f"My Groups — {total} unique group(s):")
            for g in groups:
                profiles = ", ".join(g.get("profiles", []))
                self._log(f"  {g.get('name', '?'):<40} [{profiles}]")
            self._log(_RULE)
        else:
            self._log(f"Fetch groups failed: {r.get('error', 'Unknown error')}")

    def _on_fetch_groups_profile_progress(self, r: dict, ok: bool) -> None:
        self._log(r.get("message", ""))

    def _on_batch_progress(self, r: dict, ok: bool) -> None:
        if r.get("current", 0) == 0:
            self._batch_ok = 0          # a new batch: start the count over
        self._log(r.get("message", ""))

    def _on_batch_item_result(self, r: dict, ok: bool) -> None:
        pname = r.get("profile_name", "")
        msg = r.get("message", "")
        if r.get("rate_limited", False):
            self._log(f"{_WARN} {pname}: {msg}")
        elif r.get("needs_login", False):
            self._log(f"{_CROSS} {pname}: {msg}")
        else:
            self._log(f"{_CHECK if ok else _CROSS} {pname}: {msg}")
        if ok:
            self._batch_ok += 1

    def _on_login_scan_progress(self, r: dict, ok: bool) -> None:
        self.state.scan_active = True
        self._log(r.get("message", ""))

    def _on_login_scan_result(self, r: dict, ok: bool) -> None:
        self.state.scan_active = False
        self.state.run = None
        if not r.get("ok", False):
            self._log(f"Login check failed: {r.get('error', 'Unknown error')}")
            return
        results = r.get("results", [])
        removed_profiles = r.get("removed_profiles", [])
        if removed_profiles:
            self._log(f"Auto-removed {len(removed_profiles)} disabled profile(s): "
                      + ", ".join(removed_profiles))
        logged_in_count = r.get("logged_in_count", 0)
        total = r.get("total", 0)
        needs = [n for n in (x.get("profile_name") for x in results
                             if not x.get("logged_in")) if n]
        if needs:
            names = ", ".join(needs)
            if len(names) > 90:
                names = names[:87] + "..."
            self._log(f"Login check done — {logged_in_count}/{total} logged in; "
                      f"need re-login: {names}")
        else:
            self._log(f"Login check done — {logged_in_count}/{total} logged in")

    def _on_auto_setup_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        profile_name = r.get("profile_name", "")
        if ok:
            setup = r.get("result", {}) or {}
            fb = setup.get("friends_before", 0)
            fa = setup.get("friends_added", 0)
            pic = setup.get("profile_pic_set", False) or setup.get("had_profile_pic", False)
            bio_ok = setup.get("bio_updated", False) or setup.get("had_bio", False)
            pins = setup.get("pinterest_images_downloaded", 0)
            self._log(f"✅ Auto-setup complete for '{profile_name}'\n"
                      f"   Friends: {fb} → +{fa} added\n"
                      f"   Profile pic: {'✅' if pic else '❌'}\n"
                      f"   Bio: {'✅' if bio_ok else '❌'}\n"
                      f"   Pinterest images: {pins}")
        else:
            self._log(f"❌ Auto-setup failed for '{profile_name}': "
                      f"{r.get('error', 'Unknown error')}")

    def _on_auto_setup_images_preview(self, r: dict, ok: bool) -> None:
        """The worker is now blocked on send_user_response. The window
        opened ImagePickerDialog here; the server publishes the prompt and
        lets the first device that answers /api/input close it."""
        profile_name = r.get("profile_name", "")
        images = r.get("images", []) or []
        needs_pic = r.get("needs_pic", True)
        self._log(f"🖼️ Showing image preview for '{profile_name}' "
                  f"— {len(images)} image(s)")
        allow: dict[str, str] = {}
        items = []
        for path in images:
            path = str(path)
            image_id = hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]
            allow[image_id] = path
            items.append({"id": image_id, "url": f"/api/images/{image_id}"})
        self._images = allow
        self.state.pending_input = {
            "kind": "image_picker",
            "profile_name": profile_name,
            "images": items,
            "needs_pic": bool(needs_pic),
            "created_at": time.time(),
        }
        self._log("Waiting for image choice")
        self.broadcast({"type": "needs_input", **self.state.pending_input})

    def _on_auto_setup_all_progress(self, r: dict, ok: bool) -> None:
        self._log(f"[{r.get('current', 0)}/{r.get('total', 0)}] "
                  f"{'✅' if ok else '❌'} {r.get('message', '')}")

    def _on_auto_setup_all_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        if ok:
            self._log(f"✅ Auto-setup ALL complete: "
                      f"{r.get('success_count', 0)}/{r.get('total', 0)} successful")
        else:
            self._log(f"❌ Auto-setup ALL failed: {r.get('error', 'Unknown error')}")

    def _on_batch_result(self, r: dict, ok: bool) -> None:
        total = r.get("total", 0)
        self.state.run = None
        self._log(f"Batch complete: {total} item(s) processed")
        # Every queue item ends in exactly one batch_item_result (the worker
        # reports the ones whose profile never opened too), so the failures
        # are what is left of the total once the ok items are taken out.
        ok_count = self._batch_ok
        summary = data.summary_line(ok_count, max(total - ok_count, 0))
        self.state.last_run_summary = summary
        cfg.save_setting(LAST_RUN_SUMMARY_KEY, summary)
        self._batch_ok = 0
        # queue_tab.clear_all(), as the window called it on this branch. On
        # one desktop the emptied list was simply the next thing the
        # operator saw; here it also stops a second device from pressing Run
        # on items that have already been through the browser.
        if self.queue is not None and self.queue.clear():
            self.broadcast({"type": "queue_changed"})

    def _on_fetch_groups_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        pname = r.get("profile_name", "")
        if ok:
            groups = r.get("groups", [])
            count = r.get("count", len(groups))
            self._log(_RULE)
            self._log(f"Groups for '{pname}' — {count}:")
            for g in groups:
                self._log(f"  {g.get('name', '?')}")
            self._log(_RULE)
        else:
            self._log(f"Fetch groups failed: {r.get('error', 'Unknown error')}")

    def _on_logout_result(self, r: dict, ok: bool) -> None:
        self.state.run = None
        self._log("Logged out — browser closed, credentials cleared.")

    def _on_login_accounts_progress(self, r: dict, ok: bool) -> None:
        # The route sets the flag when it queues the run; a progress event
        # is proof the run is on, so it is set here too.
        self.state.login_run_active = True
        self._log(r.get("message", ""))

    def _on_login_accounts_result(self, r: dict, ok: bool) -> None:
        self.state.login_run_active = False
        self.state.run = None
        if ok:
            self._log(f"Login run done — {len(r.get('logged_in', []))} logged in, "
                      f"{len(r.get('failed', []))} failed, "
                      f"{len(r.get('skipped', []))} skipped "
                      f"of {r.get('total', 0)}")
        else:
            self._log(f"Login run failed: {r.get('error', 'Unknown error')}")

    # ── System readout ────────────────────────────────────

    def refresh_system(self) -> None:
        """manager.get_memory_stats() -> state.system."""
        with self._lock:
            before = self.state.to_dict()
            try:
                stats = self.manager.get_memory_stats() or {}
                self._system_error = None
            except Exception as e:
                # Once per distinct failure: this runs every two seconds
                # and a log line each time would bury the run's own lines.
                stats = {}
                msg = f"{type(e).__name__}: {e}"
                if msg != self._system_error:
                    self._system_error = msg
                    self._log(f"{_CROSS} Memory stats error: {msg}")
            mem = stats.get("system_memory") or {}
            self.state.system = {
                "ram_used_gb": round(float(mem.get("used_gb") or 0), 1),
                "ram_total_gb": round(float(mem.get("total_gb") or 0), 1),
                "browser_mb": stats.get("browser_mb", 0),
                "process_count": stats.get("process_count", 0),
                "peak_browser_mb": stats.get("peak_browser_mb", 0),
            }
            if self.state.to_dict() != before:
                self._broadcast_state()

    # ── The image prompt ──────────────────────────────────

    def answer_input(self, answer: dict) -> bool:
        """Close the open prompt with {"profile_pic": id|None, "cancel":
        bool} - what ImagePickerDialog returned, with the path replaced by
        its id - and pass the path back to the worker. False when no prompt
        is open, which the route turns into 409."""
        with self._lock:
            prompt = self.state.pending_input
            if not prompt:
                return False
            cancel = bool(answer.get("cancel"))
            image_id = answer.get("profile_pic")
            path = self._images.get(image_id) if isinstance(image_id, str) else None
            self.state.pending_input = None
            self._images = {}
            self.manager.send_user_response({"profile_pic": path, "cancel": cancel})
            if cancel:
                self._log("  User cancelled image selection — using defaults")
            else:
                self._log(f"  Selected — {Path(path).name if path else '(default)'}")
            self._broadcast_state()
            return True

    def image_path(self, image_id: str) -> str | None:
        """The local file behind an id from the open prompt, or None."""
        if not isinstance(image_id, str):
            return None
        return self._images.get(image_id)

    # ── The thread ────────────────────────────────────────

    def _trace_to_file(self) -> None:
        """Append the current exception's full traceback to the daily log
        file only (not the UI ring): a one-line 'NoneType is not
        subscriptable' cannot be pinned without the stack, but a phone does
        not want the stack scrolling past. Best-effort; never raises."""
        try:
            with open(self.logring.log_path, "a", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass

    def _tick(self) -> None:
        result = self.manager.poll_result()
        while result:
            try:
                self.handle_result(result)
            except Exception as e:
                self._log(f"{_CROSS} bridge error in {result.get('type')}: "
                          f"{type(e).__name__}: {e}")
                self._trace_to_file()
            result = self.manager.poll_result()

        now = time.monotonic()
        if now - self._system_at >= SYSTEM_EVERY_S:
            self._system_at = now
            self.refresh_system()

        prompt = self.state.pending_input
        if prompt and time.time() - prompt.get("created_at", 0) >= INPUT_TIMEOUT_S:
            self._log(f"{_CROSS} No image choice for '{prompt.get('profile_name', '')}' "
                      f"within {INPUT_TIMEOUT_S // 60} min — cancelling so the "
                      f"worker can go on")
            self.answer_input({"cancel": True})

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    self._tick()
                except Exception as e:
                    # poll_result or a handler raised: log it and keep
                    # polling. The bridge never dies over one result.
                    try:
                        self._log(f"{_CROSS} bridge error: {type(e).__name__}: {e}")
                        self._trace_to_file()
                    except Exception:
                        pass
                self._stop_event.wait(self._poll_s)
        except BaseException:
            # The thread body itself is going down: say so where the
            # frontend can show the red banner, then let it die loudly.
            self.state.bridge_alive = False
            try:
                self._broadcast_state()
            except Exception:
                pass
            raise

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout)
