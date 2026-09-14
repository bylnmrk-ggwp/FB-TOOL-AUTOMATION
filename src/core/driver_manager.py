import asyncio
import gc
import math
import os
import random
import threading
import time
from enum import Enum
from queue import Empty, Queue
from typing import Callable

from groq import Groq
from playwright.async_api import async_playwright

from src.storage import config_manager as cfg
from src.storage import database as db
from src.core.facebook_automation import (
    CHROME_PATH,
    MEMORY_FLAGS,
    MICRO_VIEWPORT,
    SMALL_VIEWPORT,
    TINY_VIEWPORT,
)
from src.core.memory_tracker import MemoryTracker

# Set GROQ_API_KEY in the environment (or a local .env). Absent/invalid keys make the
# Groq calls raise, which both call sites already catch and fall back from.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


from src.core import browser_choice

class DriverState(Enum):
    STOPPED = "stopped"
    CREATING = "creating"
    STARTING = "starting"
    LOGGED_IN = "logged_in"
    SHARING = "sharing"
    ERROR = "error"


def sheet_reason(error: Exception) -> str:
    """One short line for a failed sheet write.

    The roster watcher already reduces the same urllib3 stack to "offline";
    this is its counterpart on the write side, so both speak the same way.
    """
    from src.storage.roster_sheet import _reason
    return _reason(error)


def login_reason(message: str | None) -> str | None:
    """Facebook's own words for a failed login, as a short sheet-friendly
    reason - or None when the message says nothing specific.

    The URL classification (_classify_account_access) only ever sees where
    the browser ended up, so "Input Password is invalid." and an expired
    cookie both came out as "logged out or session expired". The operator
    could not tell a bad spreadsheet password from a dead session. When the
    login itself explains the failure, that explanation wins.
    """
    m = (message or "").lower()
    if not m:
        return None
    if "password" in m and ("invalid" in m or "incorrect" in m):
        return "wrong password"
    if "still on the login form" in m:
        return "rejected at the login form"
    if "left facebook" in m:
        return "browser left Facebook"
    if ("email or mobile" in m or "email or phone" in m) and "invalid" in m:
        return "bad username"
    if "captcha" in m or "not a robot" in m:
        return "captcha"
    if "disabled" in m:
        return "disabled"
    if "checkpoint" in m:
        return "checkpoint"
    if "2fa" in m or "two-factor" in m or "two factor" in m:
        return "needs 2FA"
    if "email confirm" in m or "confirm your email" in m:
        return "needs email confirmation"
    if "never reached the home page" in m or "no home page" in m:
        return "no home page"
    if ("browser has been closed" in m or "target page" in m
            or "context or browser" in m or "launch" in m):
        return "browser error - retry"
    if "timeout" in m or "timed out" in m:
        return "needs 2FA" if "2fa" in m else "timeout - retry"
    return None


class DriverManager:
    """Drives FacebookAutomation from a background thread via a command queue.

    UI → command_queue → worker thread (async) → result_queue → UI polling

    Supports two modes:
      Single-profile mode  — _automation manages one persistent-context browser
      Concurrent mode      — _batch_automations[profile] + separate browser
                             per profile for parallel execution
    """

    def __init__(self, log_callback: Callable[[str], None] = print, debug: bool = False):
        self.cmd_queue: Queue = Queue()
        self.result_queue: Queue = Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._log = log_callback
        self._debug = debug

        # Single-profile automation (for login, share, start_profile commands)
        self._automation = None

        # Live-watch: a separate visible browser holding one window per active
        # profile on a pasted URL, kept open until stop_watch / quit.
        self._watch_pw = None
        self._watch_browser = None
        self._watch_autos: dict = {}
        # Which live each watching page is on, so one broadcast ending never
        # closes the pages watching another.
        self._watch_urls: dict = {}
        self._watch_keeper = None

        # Concurrent batch mode — each profile gets its own browser window
        self._batch_pw = None
        self._batch_automations: dict[str, "FacebookAutomation"] = {}  # noqa: F821

        self.state = DriverState.STOPPED

        # Memory tracking
        self._memory_tracker = MemoryTracker()
        self._memory_cache: dict | None = None
        self._memory_cache_time = 0.0
        self._memory_cache_ttl = 1.0  # seconds
        # JS heap cache — updated by the async worker thread, read by UI thread
        self._cached_js_heaps: dict[str, float] = {}
        # Configurable batch size — SET TO 7 for optimal balance
        # 7 profiles at once = fast but stable (3 batches total for 21 profiles)
        self._batch_size: int = cfg.get_setting("batch_size", 7)  # Balanced: not too slow, not too many
        # Tracks whether a queue/batch is actively running
        self._batch_running: bool = False
        # Response queue for user interaction (e.g., image preview selection)
        self._user_response_queue: Queue = Queue()

    @property
    def log(self):
        return self._log

    @log.setter
    def log(self, value):
        self._log = value
        if self._automation:
            self._automation.log = value
        for auto in self._batch_automations.values():
            auto.log = value

    # ── Lifecycle ──────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0):
        self._stop_event.set()
        self.cmd_queue.put({"type": "quit"})
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # ── Command helpers ───────────────────────────────────

    def login(self, profile_name: str):
        self.cmd_queue.put({"type": "login", "profile_name": profile_name})

    def start_profile(self, profile_name: str):
        self.cmd_queue.put({"type": "start_profile", "profile_name": profile_name})

    def share(self, post_url: str, group_name: str,
              comment_text: str | None = None,
              reaction: str | None = None):
        self.cmd_queue.put({
            "type": "share", "post_url": post_url, "group_name": group_name,
            "comment_text": comment_text, "reaction": reaction,
        })

    def share_to_timeline(self, post_url: str,
                          comment_text: str | None = None,
                          reaction: str | None = None):
        self.cmd_queue.put({
            "type": "share_to_timeline", "post_url": post_url,
            "comment_text": comment_text, "reaction": reaction,
        })

    def share_to_groups(self, post_url: str, groups: list[dict],
                        comment_text: str | None = None,
                        reaction: str | None = None):
        """Share a post to multiple groups (by name) at once.

        groups: list of dicts with 'name' key (group name for FB search)
        """
        self.cmd_queue.put({
            "type": "share_to_groups", "post_url": post_url,
            "groups": groups,
            "comment_text": comment_text, "reaction": reaction,
        })

    def share_to_groups_bulk(self, post_url: str, groups: list[dict],
                              comment_text: str | None = None,
                              reaction: str | None = None,
                              profile_names: list[str] | None = None):
        """Share a post to groups across ALL profiles concurrently.

        groups: list of dicts with 'name', 'url', 'profiles' keys
        profile_names narrows the run to those profiles (each group's
        'profiles' list is intersected with it); None means every profile
        the groups name.
        """
        self.cmd_queue.put({
            "type": "share_to_groups_bulk", "post_url": post_url,
            "groups": groups,
            "comment_text": comment_text, "reaction": reaction,
            "profile_names": profile_names,
        })

    def join_group(self, group_url, profile_names: list[str] | None = None):
        # profile_names scopes the bulk form; the single-URL form runs on
        # whichever context is open, so it carries the key only for a
        # uniform command shape.
        if isinstance(group_url, list):
            self.cmd_queue.put({"type": "join_group_bulk", "group_urls": group_url,
                                "profile_names": profile_names})
        else:
            self.cmd_queue.put({"type": "join_group", "group_url": group_url,
                                "profile_names": profile_names})

    def fetch_my_groups(self, profile_name: str | None = None):
        """Fetch the group list for one profile.

        profile_name selects which profile to launch; without it the open
        context is reused, or the first saved profile launched.
        """
        self.cmd_queue.put({"type": "fetch_my_groups",
                            "profile_name": profile_name})

    def fetch_my_groups_bulk(self, profile_names: list[str] | None = None):
        """Fetch groups from ALL profiles at once.

        profile_names narrows the run to those profiles; None means every
        saved profile.
        """
        self.cmd_queue.put({"type": "fetch_my_groups_bulk",
                            "profile_names": profile_names})

    def post_to_timeline(self, text: str,
                          image_paths: list[str] | None = None):
        self.cmd_queue.put({
            "type": "post_to_timeline", "text": text,
            "image_paths": image_paths,
        })

    def auto_setup_profile(self, profile_name: str,
                            target_friends: int = 50,
                            pinterest_query: str = None,
                            bio: str = None):
        self.cmd_queue.put({
            "type": "auto_setup_profile",
            "profile_name": profile_name,
            "target_friends": target_friends,
            "pinterest_query": pinterest_query,
            "bio": bio,
        })

    def auto_setup_all_profiles(self,
                                 target_friends: int = 50,
                                 pinterest_query: str = None,
                                 bio: str = None,
                                 connect_friends: bool = True,
                                 profile_names: list[str] | None = None):
        """Run auto-setup on every saved Brave profile sequentially.

        profile_names narrows the run to those profiles; None means every
        saved profile.
        """
        self.cmd_queue.put({
            "type": "auto_setup_all",
            "target_friends": target_friends,
            "pinterest_query": pinterest_query,
            "bio": bio,
            "connect_friends": connect_friends,
            "profile_names": profile_names,
        })

    def accept_all_pending_requests(self, profile_names: list[str] | None = None):
        """Check and accept pending friend requests on ALL profiles.

        profile_names narrows the run to those profiles; None means every
        saved profile.
        """
        self.cmd_queue.put({"type": "accept_all_pending",
                            "profile_names": profile_names})

    def check_login_status(self, profile_names: list[str] | None = None):
        """Live-check which saved profiles are still logged in to Facebook.

        Sequential headless scan per profile using the DOM-based check that
        detects the 'See more on Facebook' login overlay.  Emits
        login_scan_progress / login_scan_result events to the UI.
        """
        self.cmd_queue.put({
            "type": "check_login_status",
            "profile_names": profile_names,
        })

    def login_accounts(self, usernames: list[str],
                       batch_size: int | None = None,
                       pause_minutes: float | None = None):
        """Log the given roster accounts in, one at a time, and publish each
        verdict to the sheet. Emits login_accounts_progress / _result."""
        self.cmd_queue.put({"type": "login_accounts",
                            "usernames": list(usernames),
                            "batch_size": batch_size,
                            "pause_minutes": pause_minutes})

    def login_with_credentials(self, email: str, password: str):
        self.cmd_queue.put({"type": "login_with_credentials", "email": email, "password": password})

    def logout(self):
        """Clear credentials and close the browser."""
        from src.storage import config_manager as cfg
        cfg.clear_credentials()
        self.cmd_queue.put({"type": "logout"})
        self.log("Logging out and clearing session...")

    def cleanup(self):
        self.cmd_queue.put({"type": "cleanup"})

    def run_queue(self, items: list[dict]):
        self.cmd_queue.put({"type": "run_queue", "items": items})

    def watch_url(self, url: str, minutes: float | None = None,
                  profile_names: list[str] | None = None):
        """Open every active (logged-in) profile in a visible window on `url`.

        minutes bounds the watch: it stops itself after that long. None means
        run until the Stop button. profile_names narrows the watch to those
        profiles; the logged-in filter still applies on top, so a name that
        is not active is never opened.
        """
        self.cmd_queue.put({"type": "watch_url", "url": url,
                            "minutes": minutes,
                            "profile_names": profile_names})

    def stop_watch(self):
        """Close the live-watch windows."""
        self.cmd_queue.put({"type": "stop_watch"})

    def send_user_response(self, response: dict):
        """Send a user response from the UI thread to a waiting background command.

        Used for interactions like image picker preview where the background
        thread needs to pause and wait for user input.
        """
        self._user_response_queue.put(response)

    # ── Result polling (called from UI thread) ────────────

    def poll_result(self) -> dict | None:
        try:
            return self.result_queue.get_nowait()
        except Empty:
            return None

    # ── Worker loop (async) ────────────────────────────────

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_run())
        except Exception as e:
            import traceback
            self.log(f"Worker thread error: {e}\n{traceback.format_exc()}")
        finally:
            loop.close()

    async def _async_run(self):
        from src.core.facebook_automation import FacebookAutomation

        self._automation = FacebookAutomation(log_callback=self.log, debug=self._debug)

        # Keeps live sessions warm and recovers lost ones, on its own, for as
        # long as the app runs. Cancelled with the worker.
        self._sweep_task = asyncio.create_task(self._session_sweep_loop())

        # Track when we last collected JS heaps (every ~2s)
        last_js_heap_collection = 0.0
        js_heap_interval = 2.0

        while not self._stop_event.is_set():
            try:
                cmd = self.cmd_queue.get(timeout=0.3)
            except Empty:
                # Periodically collect JS heap data from the worker thread
                if time.monotonic() - last_js_heap_collection > js_heap_interval:
                    try:
                        await self._collect_js_heaps()
                    except Exception:
                        pass
                    last_js_heap_collection = time.monotonic()
                continue

            cmd_type = cmd.get("type")

            # One failing command must not end the worker. Before this, any
            # exception escaped to _run(), which logged it and let the event
            # loop close - the thread died and every later command was
            # silently ignored while the app still looked healthy. A Brave
            # auto-update mid-session was enough to trigger it.
            try:
                if cmd_type == "login":
                    await self._do_login(cmd)
                elif cmd_type == "start_profile":
                    await self._do_start_profile(cmd)
                elif cmd_type == "share":
                    await self._do_share(cmd)
                elif cmd_type == "share_to_timeline":
                    await self._do_share_timeline(cmd)
                elif cmd_type == "share_to_groups":
                    await self._do_share_to_groups(cmd)
                elif cmd_type == "share_to_groups_bulk":
                    await self._do_share_to_groups_bulk(cmd)
                elif cmd_type == "join_group":
                    await self._do_join_group(cmd)
                elif cmd_type == "join_group_bulk":
                    await self._do_join_group_bulk(cmd)
                elif cmd_type == "fetch_my_groups":
                    await self._do_fetch_my_groups(cmd)
                elif cmd_type == "fetch_my_groups_bulk":
                    await self._do_fetch_my_groups_bulk(cmd)
                elif cmd_type == "post_to_timeline":
                    await self._do_post_timeline(cmd)
                elif cmd_type == "login_with_credentials":
                    await self._do_login_with_credentials(cmd)
                elif cmd_type == "auto_setup_profile":
                    await self._do_auto_setup(cmd)
                elif cmd_type == "auto_setup_all":
                    await self._do_auto_setup_all(cmd)
                elif cmd_type == "accept_all_pending":
                    await self._do_accept_all_pending(cmd)
                elif cmd_type == "check_login_status":
                    await self._do_check_login_status(cmd)
                elif cmd_type == "login_accounts":
                    await self._do_login_accounts(cmd)
                elif cmd_type == "run_queue":
                    await self._do_batch(cmd["items"])
                elif cmd_type == "watch_url":
                    await self._do_watch(cmd["url"], cmd.get("minutes"),
                                         cmd.get("profile_names"))
                elif cmd_type == "stop_watch":
                    await self._stop_watch()
                elif cmd_type == "cleanup":
                    await self._do_cleanup()
                elif cmd_type == "logout":
                    await self._do_logout()
                elif cmd_type == "quit":
                    task = getattr(self, "_sweep_task", None)
                    if task is not None:
                        task.cancel()
                    await self._do_quit()
                    break
            except Exception as e:
                import traceback
                self.log(f"Command '{cmd_type}' failed: {e}")
                self.log(traceback.format_exc(limit=4))
                self.result_queue.put({"type": cmd_type, "success": False,
                                       "message": str(e)})

    # ── Command implementations ────────────────────────────

    async def _do_login(self, cmd: dict):
        """Add a profile: resolve Brave path, launch browser, let user log in manually."""
        self.state = DriverState.CREATING
        profile_name = cmd["profile_name"]
        brave_path = cfg.get_profile_path(profile_name)

        if not brave_path:
            self.state = DriverState.ERROR
            self.result_queue.put({
                "type": "login_result", "ok": False,
                "error": f"Profile '{profile_name}' has no Brave path",
            })
            return

        try:
            self.log(f"Starting browser for profile '{profile_name}'...")
            await self._automation.start_browser(brave_path)
            await self._automation.go_to_facebook()

            logged_in = await self._automation._is_logged_in(timeout=15)
            if logged_in:
                self.log(f"✅ Logged in as '{profile_name}'")
            else:
                self.log("⚠️ Not logged in. Log in manually in the browser.")
            self.log("Close the browser window when done to complete setup.")

            while True:
                try:
                    pages = self._automation.context.pages
                    if len(pages) == 0:
                        break
                    await asyncio.sleep(0.5)
                except Exception:
                    break

            await self._automation.quit()
            self.state = DriverState.STOPPED
            self.result_queue.put({
                "type": "login_result", "ok": True,
                "profile_name": profile_name, "needs_login": not logged_in,
            })
            self.log(f"Profile '{profile_name}' setup complete")
        except Exception as e:
            self.state = DriverState.ERROR
            self.result_queue.put({"type": "login_result", "ok": False, "error": str(e)})
            self.log(f"Profile setup failed: {e}")

    async def _do_start_profile(self, cmd: dict):
        """Start an existing profile: launch browser and check login state."""
        self.state = DriverState.STARTING
        profile_name = cmd["profile_name"]
        brave_path = cfg.get_profile_path(profile_name)

        if not brave_path:
            self.state = DriverState.ERROR
            self.result_queue.put({
                "type": "login_result", "ok": False,
                "error": f"Profile '{profile_name}' has no Brave path",
            })
            return

        try:
            if self._automation.context:
                self.log(f"Closing existing browser to launch profile '{profile_name}'...")
                await self._automation.cleanup()
                await asyncio.sleep(1)

            self.log(f"Launching profile '{profile_name}'...")
            await self._automation.start_browser(brave_path)
            await self._automation.go_to_facebook()

            logged_in = await self._automation._is_logged_in(timeout=15)
            if logged_in:
                self.state = DriverState.LOGGED_IN
                self.log(f"Profile '{profile_name}' — logged in")
                self.result_queue.put({
                    "type": "login_result", "ok": True, "profile_name": profile_name,
                })
            else:
                self.state = DriverState.LOGGED_IN
                self.log("Not logged in. Please log in manually in the browser.")
                self.result_queue.put({
                    "type": "login_result", "ok": True,
                    "profile_name": profile_name, "needs_login": True,
                })
        except Exception as e:
            self.state = DriverState.ERROR
            self.result_queue.put({"type": "login_result", "ok": False, "error": str(e)})

    async def _auto_launch_first_profile(self, profile_name: str | None = None) -> bool:
        """Auto-launch a saved profile's browser.

        Called with no argument this behaves as it always has: launch the first
        saved profile, for callers that only reach here when no context is open.
        Pass profile_name to launch that specific profile instead, replacing any
        context already open so the caller really gets the profile it asked for.
        Returns True if a profile was successfully launched."""
        profiles = cfg.list_profiles()
        if not profiles:
            return False
        if profile_name is None:
            profile_name = profiles[0]
        elif profile_name not in profiles:
            self.log(f"Profile '{profile_name}' is not saved")
            return False
        brave_path = cfg.get_profile_path(profile_name)
        if not brave_path:
            return False
        try:
            if self._automation.context:
                self.log(f"Closing existing browser to launch '{profile_name}'...")
                await self._automation.cleanup()
                await asyncio.sleep(1)
            self.log(f"Auto-launching profile '{profile_name}'...")
            await self._automation.start_browser(brave_path)
            await self._automation.go_to_facebook()
            logged_in = await self._automation._is_logged_in(timeout=15)
            if not logged_in:
                self.log(f"Profile '{profile_name}' not logged in — cannot auto-launch")
                await self._automation.cleanup()
                return False
            self.log(f"Profile '{profile_name}' launched and logged in")
            return True
        except Exception as e:
            self.log(f"Auto-launch failed: {e}")
            try:
                await self._automation.cleanup()
            except Exception:
                pass
            return False

    async def _do_share(self, cmd: dict):
        if not self._automation.context:
            launched = await self._auto_launch_first_profile()
            if not launched:
                self.result_queue.put({
                    "type": "share_result", "ok": False,
                    "error": "No profile available. Add a profile first.",
                })
                return

        self.state = DriverState.SHARING
        try:
            ok, msg = await self._automation.share_post_to_group(
                cmd["post_url"], cmd["group_name"],
                comment_text=cmd.get("comment_text"),
                reaction=cmd.get("reaction"),
            )
            if ok:
                await self._automation.cleanup()
                self.state = DriverState.LOGGED_IN
                self.result_queue.put({"type": "share_result", "ok": True, "message": msg})
            else:
                self.state = DriverState.LOGGED_IN
                self.result_queue.put({"type": "share_result", "ok": False, "message": msg})
        except Exception as e:
            self.state = DriverState.LOGGED_IN
            self.result_queue.put({"type": "share_result", "ok": False, "error": str(e)})

    async def _do_share_timeline(self, cmd: dict):
        if not self._automation.context:
            launched = await self._auto_launch_first_profile()
            if not launched:
                self.result_queue.put({
                    "type": "share_result", "ok": False,
                    "error": "No profile available. Add a profile first.",
                })
                return

        self.state = DriverState.SHARING
        try:
            ok, msg = await self._automation.share_post_to_timeline(
                cmd["post_url"],
                comment_text=cmd.get("comment_text"),
                reaction=cmd.get("reaction"),
            )
            if ok:
                await self._automation.cleanup()
                self.state = DriverState.LOGGED_IN
                self.result_queue.put({"type": "share_result", "ok": True, "message": msg})
            else:
                self.state = DriverState.LOGGED_IN
                self.result_queue.put({"type": "share_result", "ok": False, "message": msg})
        except Exception as e:
            self.state = DriverState.LOGGED_IN
            self.result_queue.put({"type": "share_result", "ok": False, "error": str(e)})

    async def _do_share_to_groups(self, cmd: dict):
        """Share a post to multiple groups using the current profile."""
        if not self._automation.context:
            launched = await self._auto_launch_first_profile()
            if not launched:
                self.result_queue.put({
                    "type": "share_result", "ok": False,
                    "error": "No profile available. Add a profile first.",
                })
                return

        post_url = cmd["post_url"]
        groups = cmd.get("groups", [])
        comment_text = cmd.get("comment_text")
        reaction = cmd.get("reaction")

        if not groups:
            self.result_queue.put({
                "type": "share_result", "ok": False,
                "error": "No groups selected.",
            })
            return

        self.state = DriverState.SHARING
        total = len(groups)
        success = 0
        failed = 0

        self.log(f"Sharing to {total} group(s)...")

        # The single-profile share always runs on the first saved profile —
        # the same one _auto_launch_first_profile() launches when no context is
        # open. No command field carries the profile name, so resolve it here
        # instead of recording share history under "".
        profiles = cfg.list_profiles()
        profile_name = profiles[0] if profiles else ""
        skipped = 0

        for i, g in enumerate(groups, 1):
            group_name = g.get("name", "")

            if db.has_shared(profile_name, post_url, group_name):
                self.log(f"[{i}/{total}] Already shared to '{group_name}', skipping.")
                skipped += 1
                self.result_queue.put({
                    "type": "share_progress",
                    "current": i, "total": total,
                    "message": f"[{i}/{total}] {group_name} (skipped - already shared)",
                })
                continue

            self.result_queue.put({
                "type": "share_progress",
                "current": i, "total": total,
                "message": f"[{i}/{total}] {group_name}",
            })

            try:
                ok, msg = await self._automation.share_post_to_group(
                    post_url, group_name,
                    comment_text=comment_text,
                    reaction=reaction,
                    skip_timeline=(i > 1),
                    skip_reaction=(i > 1),
                )
                if ok:
                    success += 1
                    db.record_share(profile_name, post_url, group_name, "shared", msg)
                else:
                    failed += 1
                    db.record_share(profile_name, post_url, group_name, "failed", msg)
                self.result_queue.put({
                    "type": "share_result",
                    "ok": ok, "message": msg,
                    "group_name": group_name,
                    "current": i, "total": total,
                })
            except Exception as e:
                failed += 1
                db.record_share(profile_name, post_url, group_name, "error", str(e))
                self.result_queue.put({
                    "type": "share_result",
                    "ok": False, "error": str(e),
                    "group_name": group_name,
                    "current": i, "total": total,
                })

            # Add configurable delay between shares to avoid spam detection
            if i < total:
                delays = cfg.get_share_delays()
                delay = random.uniform(delays["between_shares_min"], delays["between_shares_max"])
                self.log(f"Waiting {delay:.1f}s before next share...")
                await asyncio.sleep(delay)

        await self._automation.cleanup()
        self.state = DriverState.LOGGED_IN
        self.result_queue.put({
            "type": "share_bulk_result",
            "ok": True,
            "message": f"Done — {success} shared, {failed} failed, {skipped} skipped out of {total}",
            "success": success, "failed": failed, "total": total, "skipped": skipped,
        })

    async def _do_share_to_groups_bulk(self, cmd: dict):
        """Share a post to groups across ALL profiles concurrently using shared browser."""
        from src.core.facebook_automation import FacebookAutomation

        post_url = cmd["post_url"]
        groups = cmd.get("groups", [])
        comment_text = cmd.get("comment_text")
        reaction = cmd.get("reaction")

        if not groups:
            self.result_queue.put({
                "type": "share_bulk_result", "ok": False,
                "error": "No groups selected.",
            })
            return

        # An explicit profile list narrows each group's 'profiles' to the
        # requested set. Done after the empty-groups check so a request that
        # matches no profile is reported as such below, not as "no groups".
        wanted = cmd.get("profile_names")
        if wanted:
            keep = set(wanted)
            groups = [dict(g, profiles=[p for p in g.get("profiles", []) if p in keep])
                      for g in groups]
            groups = [g for g in groups if g["profiles"]]

        # Group groups by profile
        profile_groups: dict[str, list[dict]] = {}
        for g in groups:
            for pname in g.get("profiles", []):
                profile_groups.setdefault(pname, []).append(g)

        if not profile_groups:
            self.result_queue.put({
                "type": "share_bulk_result", "ok": False,
                "error": "No profiles found for selected groups.",
            })
            return

        self.state = DriverState.SHARING
        self._batch_running = True
        total_profiles = len(profile_groups)
        total_groups = len(groups)
        self.log(f"Bulk sharing to {total_groups} group(s) across {total_profiles} profile(s)...")

        batch_pw = None
        shared_browser = None

        try:
            # Phase 1: Extract storage states
            self.log("Phase 1: Extracting login states...")
            self.result_queue.put({
                "type": "share_bulk_profile_progress",
                "current": 0, "total": total_profiles,
                "profile_name": "", "ok": True,
                "message": "Extracting login states...",
            })

            states: dict[str, dict | None] = {}
            for p_idx, pname in enumerate(profile_groups.keys()):
                brave_path = cfg.get_profile_path(pname)
                if not brave_path:
                    states[pname] = None
                    self.result_queue.put({
                        "type": "share_bulk_profile_progress",
                        "current": p_idx + 1, "total": total_profiles,
                        "profile_name": pname, "ok": False,
                        "message": f"Profile '{pname}' — no Brave path, skipping",
                    })
                    continue

                self.log(f"  [{p_idx+1}/{total_profiles}] Extracting '{pname}'...")
                temp_auto = self._create_temp_automation()
                try:
                    state = await temp_auto.extract_storage_state(brave_path)
                    states[pname] = state
                    self.result_queue.put({
                        "type": "share_bulk_profile_progress",
                        "current": p_idx + 1, "total": total_profiles,
                        "profile_name": pname,
                        "ok": state is not None,
                        "message": f"[{p_idx+1}/{total_profiles}] Profile '{pname}' — {'OK' if state else 'failed'}",
                    })
                except Exception as e:
                    self.log(f"  Failed to extract '{pname}': {e}")
                    states[pname] = None

            # Phase 2: Launch shared browser
            self.log("Phase 2: Launching shared browser...")
            batch_pw = await async_playwright().start()
            shared_browser = await batch_pw.chromium.launch(
                executable_path=browser_choice.executable_path(),
                headless=True,
                args=[
                    f"--window-size={TINY_VIEWPORT['width']},{TINY_VIEWPORT['height']}",
                    *MEMORY_FLAGS,
                ],
            )

            # Phase 3: Share concurrently
            active_profiles = [p for p in profile_groups if states.get(p) is not None]
            self.log(f"Phase 3: Sharing from {len(active_profiles)} profile(s)...")

            # Limit concurrent contexts to avoid Facebook rate limiting
            _sem_share = asyncio.Semaphore(3)

            async def _share_one(profile_name: str, p_idx: int) -> dict:
                async with _sem_share:
                    auto = FacebookAutomation(log_callback=self.log, debug=self._debug)
                    my_groups = profile_groups[profile_name]
                    success = 0
                    failed = 0
                    skipped = 0
                    try:
                        await auto.init_from_storage(shared_browser, states[profile_name], viewport=TINY_VIEWPORT)
                        await asyncio.sleep(p_idx * 8)
                        await auto.go_to_facebook()
                        logged_in = await auto._is_logged_in(timeout=15)
                        if not logged_in:
                            return {"profile_name": profile_name, "ok": False,
                                    "success": 0, "failed": 0, "skipped": 0,
                                    "error": "Not logged in"}

                        for gi, g in enumerate(my_groups, 1):
                            gname = g.get("name", "")
                            if db.has_shared(profile_name, post_url, gname):
                                self.log(f"  [{profile_name}] [{gi}/{len(my_groups)}] Already shared to '{gname}', skipping.")
                                skipped += 1
                                continue

                            try:
                                ok, msg = await auto.share_post_to_group(
                                    post_url, gname,
                                    comment_text=comment_text,
                                    reaction=reaction,
                                    skip_timeline=(gi > 1),
                                    skip_reaction=(gi > 1),
                                )
                                if ok:
                                    success += 1
                                    db.record_share(profile_name, post_url, gname, "shared", msg)
                                else:
                                    failed += 1
                                    db.record_share(profile_name, post_url, gname, "failed", msg)
                            except Exception as e:
                                failed += 1
                                db.record_share(profile_name, post_url, gname, "error", str(e))

                            # Add configurable delay between shares to avoid spam detection
                            if gi < len(my_groups):
                                from src.storage import config_manager as cfg
                                delays = cfg.get_share_delays()
                                delay = random.uniform(delays["between_shares_min"], delays["between_shares_max"])
                                await asyncio.sleep(delay)

                        return {"profile_name": profile_name, "ok": True,
                                "success": success, "failed": failed, "skipped": skipped}
                    except Exception as e:
                        return {"profile_name": profile_name, "ok": False,
                                "success": 0, "failed": 0, "skipped": 0,
                                "error": str(e)}
                    finally:
                        try:
                            await auto.close_context()
                        except Exception:
                            pass

            tasks = [_share_one(name, idx) for idx, name in enumerate(active_profiles)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            total_success = 0
            total_failed = 0
            total_skipped = 0

            for r in results:
                if isinstance(r, Exception):
                    total_failed += 1
                    continue
                total_success += r.get("success", 0)
                total_failed += r.get("failed", 0)
                total_skipped += r.get("skipped", 0)
                pname = r["profile_name"]
                icon = "OK" if r.get("ok") else "FAIL"
                detail = r.get("error", f"{r.get('success',0)} shared, {r.get('failed',0)} failed, {r.get('skipped',0)} skipped")
                self.log(f"  {icon} {pname}: {detail}")
                self.result_queue.put({
                    "type": "share_bulk_profile_result",
                    "profile_name": pname,
                    "ok": r.get("ok", False),
                    "message": detail,
                })

            self.result_queue.put({
                "type": "share_bulk_result",
                "ok": True,
                "message": f"Done — {total_success} shared, {total_failed} failed, {total_skipped} skipped out of {total_groups}",
                "success": total_success, "failed": total_failed,
                "total": total_groups, "skipped": total_skipped,
            })

        except Exception as e:
            self.log(f"Bulk share error: {e}")
            self.result_queue.put({
                "type": "share_bulk_result", "ok": False,
                "error": str(e),
            })
        finally:
            self._batch_running = False
            if shared_browser:
                try:
                    await shared_browser.close()
                except Exception:
                    pass
            if batch_pw:
                try:
                    await batch_pw.stop()
                except Exception:
                    pass
            self.state = DriverState.LOGGED_IN

    async def _do_fetch_my_groups(self, cmd: dict):
        """Fetch groups for one profile.

        With a profile_name, that profile's browser is launched (replacing any
        open context) so the groups returned really belong to it.  Without one,
        the already-open context is reused, or the first saved profile launched.
        """
        requested = cmd.get("profile_name")
        if requested:
            launched = await self._auto_launch_first_profile(requested)
            if not launched:
                self.result_queue.put({
                    "type": "fetch_groups_result", "ok": False,
                    "profile_name": requested,
                    "error": f"Could not launch profile '{requested}'.",
                })
                return
        elif not self._automation.context:
            launched = await self._auto_launch_first_profile()
            if not launched:
                self.result_queue.put({
                    "type": "fetch_groups_result", "ok": False,
                    "error": "No profile available. Add a profile first.",
                })
                return

        _profiles = cfg.list_profiles()
        profile_name = requested or (_profiles[0] if _profiles else "unknown")
        self.state = DriverState.SHARING
        try:
            groups = await self._automation.fetch_my_groups()
            self.result_queue.put({
                "type": "fetch_groups_result", "ok": True,
                "profile_name": profile_name,
                "groups": groups,
                "count": len(groups),
            })
        except Exception as e:
            self.result_queue.put({
                "type": "fetch_groups_result", "ok": False,
                "profile_name": profile_name,
                "error": str(e),
            })
        finally:
            self.state = DriverState.LOGGED_IN

    async def _do_fetch_my_groups_bulk(self, cmd: dict):
        """Fetch groups from ALL profiles using the shared-browser batch approach."""
        from src.core.facebook_automation import FacebookAutomation

        profiles = cmd.get("profile_names") or cfg.list_profiles()
        if not profiles:
            self.result_queue.put({
                "type": "fetch_groups_bulk_result", "ok": False,
                "error": "No profiles available.",
            })
            return

        self.state = DriverState.SHARING
        self._batch_running = True
        total_profiles = len(profiles)

        self.log(f"Fetching groups from {total_profiles} profile(s)...")

        batch_pw = None
        shared_browser = None

        try:
            # Phase 1: Extract storage states
            self.log("Phase 1: Extracting login states...")
            self.result_queue.put({
                "type": "fetch_groups_profile_progress",
                "current": 0, "total": total_profiles,
                "profile_name": "", "ok": True,
                "message": "Extracting login states...",
            })

            states: dict[str, dict | None] = {}
            for p_idx, profile_name in enumerate(profiles):
                brave_path = cfg.get_profile_path(profile_name)
                if not brave_path:
                    states[profile_name] = None
                    self.result_queue.put({
                        "type": "fetch_groups_profile_progress",
                        "current": p_idx + 1, "total": total_profiles,
                        "profile_name": profile_name, "ok": False,
                        "message": f"Profile '{profile_name}' — no Brave path, skipping",
                    })
                    continue

                self.log(f"  [{p_idx+1}/{total_profiles}] Extracting '{profile_name}'...")
                temp_auto = self._create_temp_automation()
                try:
                    state = await temp_auto.extract_storage_state(brave_path)
                    states[profile_name] = state
                    self.result_queue.put({
                        "type": "fetch_groups_profile_progress",
                        "current": p_idx + 1, "total": total_profiles,
                        "profile_name": profile_name,
                        "ok": state is not None,
                        "message": f"[{p_idx+1}/{total_profiles}] Profile '{profile_name}' — {'OK' if state else 'failed'}",
                    })
                except Exception as e:
                    self.log(f"  ❌ Failed to extract '{profile_name}': {e}")
                    states[profile_name] = None

            # Phase 2: Launch shared browser
            self.log("Phase 2: Launching shared browser...")
            batch_pw = await async_playwright().start()
            shared_browser = await batch_pw.chromium.launch(
                executable_path=browser_choice.executable_path(),
                headless=True,
                args=[
                    f"--window-size={TINY_VIEWPORT['width']},{TINY_VIEWPORT['height']}",
                    *MEMORY_FLAGS,
                ],
            )

            # Phase 3: Fetch groups concurrently
            active_profiles = [p for p in profiles if states.get(p) is not None]
            self.log(f"Phase 3: Fetching from {len(active_profiles)} profile(s)...")

            # Limit concurrent contexts to avoid Facebook rate limiting
            _sem_fetch = asyncio.Semaphore(3)

            async def _fetch_one(profile_name: str, p_idx: int) -> dict:
                async with _sem_fetch:
                    auto = FacebookAutomation(log_callback=self.log, debug=self._debug)
                    try:
                        await auto.init_from_storage(shared_browser, states[profile_name], viewport=TINY_VIEWPORT)
                        await asyncio.sleep(p_idx * 5)
                        await auto.go_to_facebook()
                        logged_in = await auto._is_logged_in(timeout=15)
                        if not logged_in:
                            return {"profile_name": profile_name, "ok": False,
                                    "groups": [], "error": "Not logged in"}

                        groups = await auto.fetch_my_groups()
                        return {"profile_name": profile_name, "ok": True, "groups": groups}
                    except Exception as e:
                        return {"profile_name": profile_name, "ok": False,
                                "groups": [], "error": str(e)}
                    finally:
                        try:
                            await auto.close_context()
                        except Exception:
                            pass

            tasks = [_fetch_one(name, idx) for idx, name in enumerate(active_profiles)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Merge and deduplicate
            all_groups: dict[str, dict] = {}  # url -> {name, url, profiles: []}
            per_profile: dict[str, list[dict]] = {}  # profile -> [{name, url}]

            for r in results:
                if isinstance(r, Exception):
                    continue
                pname = r["profile_name"]
                profile_groups = []
                for g in r.get("groups", []):
                    url = g["url"]
                    profile_groups.append({"name": g["name"], "url": url})
                    if url not in all_groups:
                        all_groups[url] = {"name": g["name"], "url": url, "profiles": []}
                    if pname not in all_groups[url]["profiles"]:
                        all_groups[url]["profiles"].append(pname)
                per_profile[pname] = profile_groups

            # Save each profile's groups to DB
            for pname, pgroups in per_profile.items():
                if pgroups:
                    db.save_profile_groups(pname, pgroups)
                    self.log(f"  Saved {len(pgroups)} group(s) for '{pname}' to database")

            deduplicated = sorted(all_groups.values(), key=lambda g: g["name"].lower())

            self.log(f"Found {len(deduplicated)} unique group(s) across {len(active_profiles)} profile(s)")

            self.result_queue.put({
                "type": "fetch_groups_bulk_result",
                "ok": True,
                "groups": deduplicated,
                "total_groups": len(deduplicated),
                "total_profiles": len(active_profiles),
            })

        except Exception as e:
            self.log(f"Bulk fetch groups failed: {e}")
            self.result_queue.put({
                "type": "fetch_groups_bulk_result", "ok": False,
                "error": str(e),
            })
        finally:
            if shared_browser:
                try:
                    await shared_browser.close()
                except Exception:
                    pass
            if batch_pw:
                try:
                    await batch_pw.stop()
                except Exception:
                    pass
            self._batch_running = False

    async def _do_join_group(self, cmd: dict):
        if not self._automation.context:
            launched = await self._auto_launch_first_profile()
            if not launched:
                self.result_queue.put({
                    "type": "join_group_result", "ok": False,
                    "error": "No profile available. Add a profile first.",
                })
                return

        group_url = cmd["group_url"]
        _profiles = cfg.list_profiles()
        profile_name = _profiles[0] if _profiles else "unknown"

        if db.has_joined(profile_name, group_url):
            self.result_queue.put({
                "type": "join_group_result", "ok": True,
                "message": "Already a member — skipped",
                "skipped": True,
            })
            return

        self.state = DriverState.SHARING
        try:
            ok, msg = await self._automation.join_group(group_url)
            if ok:
                if "already" in msg.lower():
                    status = "already_member"
                elif "pending" in msg.lower() or "requested" in msg.lower():
                    status = "pending"
                else:
                    status = "joined"
            else:
                status = "failed"
            db.record_join(profile_name, group_url, status, msg)
            await self._automation.cleanup()
            self.state = DriverState.LOGGED_IN
            self.result_queue.put({"type": "join_group_result", "ok": ok, "message": msg})
        except Exception as e:
            db.record_join(profile_name, group_url, "error", str(e))
            self.state = DriverState.LOGGED_IN
            self.result_queue.put({"type": "join_group_result", "ok": False, "error": str(e)})

    async def _do_join_group_bulk(self, cmd: dict):
        from src.core.facebook_automation import FacebookAutomation

        urls = cmd.get("group_urls", [])
        if not urls:
            self.result_queue.put({
                "type": "join_group_bulk_result", "ok": False,
                "error": "No URLs provided.",
            })
            return

        profiles = cmd.get("profile_names") or cfg.list_profiles()
        if not profiles:
            self.result_queue.put({
                "type": "join_group_bulk_result", "ok": False,
                "error": "No profiles available. Add a profile first.",
            })
            return

        self.state = DriverState.SHARING
        total_urls = len(urls)
        total_profiles = len(profiles)
        self._batch_running = True

        self.log(f"Starting bulk join: {total_profiles} profile(s), {total_urls} group(s) each")

        batch_pw = None
        shared_browser = None
        batch_automations: dict[str, FacebookAutomation] = {}

        try:
            # ── Phase 1: Extract storage states (sequential, one at a time) ──
            self.log("Phase 1: Extracting login states...")
            self.result_queue.put({
                "type": "join_group_profile_progress",
                "current": 0, "total": total_profiles,
                "profile_name": "", "ok": True,
                "message": "Extracting login states...",
            })

            states: dict[str, dict | None] = {}
            for p_idx, profile_name in enumerate(profiles):
                brave_path = cfg.get_profile_path(profile_name)
                if not brave_path:
                    self.log(f"  Profile '{profile_name}' — no Brave path, skipping")
                    self.result_queue.put({
                        "type": "join_group_profile_progress",
                        "current": p_idx + 1, "total": total_profiles,
                        "profile_name": profile_name, "ok": False,
                        "message": f"Profile '{profile_name}' — no Brave path, skipping",
                    })
                    states[profile_name] = None
                    continue

                self.log(f"  [{p_idx+1}/{total_profiles}] Extracting '{profile_name}'...")
                temp_auto = self._create_temp_automation()
                try:
                    state = await temp_auto.extract_storage_state(brave_path)
                    if state is None:
                        self.log(f"  ⚠️  Could not extract state for '{profile_name}'")
                        self.result_queue.put({
                            "type": "join_group_profile_progress",
                            "current": p_idx + 1, "total": total_profiles,
                            "profile_name": profile_name, "ok": False,
                            "message": f"Profile '{profile_name}' — could not extract login state",
                        })
                    else:
                        self.log(f"  [{p_idx+1}/{total_profiles}] '{profile_name}' state extracted OK")
                        self.result_queue.put({
                            "type": "join_group_profile_progress",
                            "current": p_idx + 1, "total": total_profiles,
                            "profile_name": profile_name, "ok": True,
                            "message": f"[{p_idx+1}/{total_profiles}] Profile '{profile_name}' — login state OK",
                        })
                    states[profile_name] = state
                except Exception as e:
                    self.log(f"  ❌ Failed to extract '{profile_name}': {e}")
                    states[profile_name] = None

            # ── Phase 2: Launch ONE shared browser ──
            self.log("Phase 2: Launching shared browser...")
            self.result_queue.put({
                "type": "join_group_profile_progress",
                "current": 0, "total": total_profiles,
                "profile_name": "", "ok": True,
                "message": "Launching shared browser...",
            })

            batch_pw = await async_playwright().start()
            shared_browser = await batch_pw.chromium.launch(
                executable_path=browser_choice.executable_path(),
                headless=True,
                args=[
                    f"--window-size={TINY_VIEWPORT['width']},{TINY_VIEWPORT['height']}",
                    *MEMORY_FLAGS,
                ],
            )

            # ── Phase 3: Create contexts and join concurrently ──
            active_profiles = [p for p in profiles if states.get(p) is not None]
            self.log(f"Phase 3: Running {len(active_profiles)} profile(s) concurrently...")
            
            # Limit concurrent contexts to avoid Facebook rate limiting and timeouts
            MAX_CONCURRENT_CONTEXTS = 3  # Max 3 profiles joining at once
            _sem = asyncio.Semaphore(MAX_CONCURRENT_CONTEXTS)
            self.log(f"  Max {MAX_CONCURRENT_CONTEXTS} concurrent contexts to avoid timeouts")

            for profile_name in active_profiles:
                state = states.get(profile_name)
                auto = FacebookAutomation(log_callback=self.log, debug=self._debug)
                await auto.init_from_storage(shared_browser, state, viewport=TINY_VIEWPORT)
                batch_automations[profile_name] = auto

            async def _join_one(profile_name: str, p_idx: int) -> dict:
                async with _sem:  # Limit concurrent operations
                    auto = batch_automations.get(profile_name)
                    if not auto:
                        return {"ok": False, "profile_name": profile_name,
                                "error": "Context not available", "success": 0,
                                "failed": 0, "skipped": 0}

                    profile_success = 0
                    profile_failed = 0
                    profile_skipped = 0

                    try:
                        # Stagger: each profile waits before starting
                        await asyncio.sleep(p_idx * 4)

                        await auto.go_to_facebook()
                        logged_in = await auto._is_logged_in(timeout=15)
                        if not logged_in:
                            return {"ok": False, "profile_name": profile_name,
                                    "error": "Not logged in", "success": 0,
                                    "failed": 0, "skipped": 0}

                        self.log(f"  '{profile_name}' logged in — joining {total_urls} groups...")
                        consecutive_timeouts = 0

                        for i, url in enumerate(urls, 1):
                            self.result_queue.put({
                                "type": "join_group_progress",
                                "profile_name": profile_name,
                                "current": i, "total": total_urls,
                                "message": f"{profile_name} — [{i}/{total_urls}] {url}",
                            })

                            if db.has_joined(profile_name, url):
                                profile_skipped += 1
                                self.log(f"    '{profile_name}' already joined {url} — skipping")
                                self.result_queue.put({
                                    "type": "join_group_item_result",
                                    "ok": True, "message": "Already joined — skipped",
                                    "url": url, "profile_name": profile_name,
                                    "current": i, "total": total_urls,
                                    "skipped": True,
                                })
                                consecutive_timeouts = 0
                                continue

                            try:
                                ok, msg = await auto.join_group(url)
                                if ok:
                                    if "already" in msg.lower():
                                        status = "already_member"
                                        profile_skipped += 1
                                        consecutive_timeouts = 0
                                    elif "pending" in msg.lower() or "requested" in msg.lower():
                                        status = "pending"
                                        profile_success += 1
                                        consecutive_timeouts = 0
                                    else:
                                        status = "joined"
                                        profile_success += 1
                                        consecutive_timeouts = 0
                                else:
                                    status = "failed"
                                    profile_failed += 1
                                    if "timeout" in msg.lower() or "timed out" in msg.lower():
                                        consecutive_timeouts += 1
                                    else:
                                        consecutive_timeouts = 0

                                db.record_join(profile_name, url, status, msg)
                                self.result_queue.put({
                                    "type": "join_group_item_result",
                                    "ok": ok, "message": msg, "url": url,
                                    "profile_name": profile_name,
                                    "current": i, "total": total_urls,
                                })
                            except Exception as e:
                                profile_failed += 1
                                db.record_join(profile_name, url, "error", str(e))
                                self.result_queue.put({
                                    "type": "join_group_item_result",
                                    "ok": False, "error": str(e), "url": url,
                                    "profile_name": profile_name,
                                    "current": i, "total": total_urls,
                                })
                                consecutive_timeouts += 1

                            # Adaptive delay: back off after consecutive timeouts.
                            # Tunable via CONFIGURE_DELAYS.bat like the share delays.
                            jd = cfg.get_share_delays()
                            if consecutive_timeouts >= 3:
                                delay = random.uniform(jd["join_backoff_min"], jd["join_backoff_max"])
                                self.log(f"  '{profile_name}' {consecutive_timeouts} timeouts — backing off {delay:.0f}s")
                                consecutive_timeouts = 0
                            elif consecutive_timeouts >= 1:
                                delay = random.uniform(jd["join_retry_min"], jd["join_retry_max"])
                            else:
                                delay = random.uniform(jd["between_joins_min"], jd["between_joins_max"])

                            if i < total_urls:
                                await asyncio.sleep(delay)

                        self.log(f"  '{profile_name}' done: {profile_success} joined, {profile_failed} failed, {profile_skipped} skipped")
                        return {"ok": True, "profile_name": profile_name,
                                "success": profile_success, "failed": profile_failed,
                                "skipped": profile_skipped}

                    except Exception as e:
                        return {"ok": False, "profile_name": profile_name,
                                "error": str(e), "success": 0, "failed": total_urls,
                                "skipped": 0}

            tasks = [_join_one(name, idx) for idx, name in enumerate(active_profiles)]
            profile_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect results
            overall_success = 0
            overall_failed = 0
            overall_skipped = 0
            cleaned_results = []
            for r in profile_results:
                if isinstance(r, Exception):
                    cleaned_results.append({"ok": False, "profile_name": "?",
                                            "error": str(r), "success": 0,
                                            "failed": 0, "skipped": 0})
                    overall_failed += total_urls
                else:
                    cleaned_results.append(r)
                    overall_success += r.get("success", 0)
                    overall_failed += r.get("failed", 0)
                    overall_skipped += r.get("skipped", 0)

            # Add skipped profiles
            for p in profiles:
                if p not in active_profiles:
                    cleaned_results.append({"ok": False, "profile_name": p,
                                            "error": "Not logged in or no path",
                                            "success": 0, "failed": 0, "skipped": 0})

            db.log_activity("bulk_join", details=(
                f"{total_urls} groups x {total_profiles} profiles — "
                f"{overall_success} joined, {overall_failed} failed, {overall_skipped} skipped"
            ))

            self.state = DriverState.STOPPED
            self.result_queue.put({
                "type": "join_group_bulk_result",
                "ok": True,
                "message": (f"Done — {overall_success} joined, {overall_failed} failed, "
                            f"{overall_skipped} skipped across {total_profiles} profile(s)"),
                "success": overall_success, "failed": overall_failed,
                "skipped": overall_skipped,
                "total_profiles": total_profiles,
                "total_urls": total_urls,
                "profile_results": cleaned_results,
            })

        except Exception as e:
            self.log(f"Bulk join failed: {e}")
            self.state = DriverState.STOPPED
            self.result_queue.put({
                "type": "join_group_bulk_result", "ok": False,
                "error": str(e),
            })
        finally:
            # ── Cleanup ──
            for auto in batch_automations.values():
                try:
                    await auto.close_context()
                except Exception:
                    pass
            if shared_browser:
                try:
                    await shared_browser.close()
                except Exception:
                    pass
            if batch_pw:
                try:
                    await batch_pw.stop()
                except Exception:
                    pass
            self._batch_running = False

    async def _do_post_timeline(self, cmd: dict):
        """Post text (optionally with images) to timeline."""
        if not self._automation.context:
            launched = await self._auto_launch_first_profile()
            if not launched:
                self.result_queue.put({
                    "type": "share_result", "ok": False,
                    "error": "No profile available. Add a profile first.",
                })
                return

        self.state = DriverState.SHARING
        try:
            ok, msg = await self._automation.post_text_to_timeline(
                cmd["text"],
                image_paths=cmd.get("image_paths"),
            )
            if ok:
                await self._automation.cleanup()
                self.state = DriverState.LOGGED_IN
                self.result_queue.put({"type": "share_result", "ok": True, "message": msg})
            else:
                self.state = DriverState.LOGGED_IN
                self.result_queue.put({"type": "share_result", "ok": False, "message": msg})
        except Exception as e:
            self.state = DriverState.LOGGED_IN
            self.result_queue.put({"type": "share_result", "ok": False, "error": str(e)})

    async def _do_login_with_credentials(self, cmd: dict):
        email = cmd["email"]
        password = cmd["password"]

        self.state = DriverState.STARTING
        try:
            import tempfile
            import os

            if self._automation.context:
                self.log("Closing existing browser before credential login...")
                await self._automation.cleanup()

            attempt_id = str(int(time.time()))
            tmp_profile = os.path.join(tempfile.gettempdir(), f"autoshare_cred_{attempt_id}")
            os.makedirs(tmp_profile, exist_ok=True)

            self.log("Starting browser for credential login...")
            await self._automation.start_browser_headless(tmp_profile)  # Background mode
            await self._automation.go_to_facebook()

            self.log(f"Logging in as '{email}'...")
            ok, msg = await self._automation.login_with_credentials(email, password)

            if ok:
                self.state = DriverState.LOGGED_IN
                self.log(msg)
                self.result_queue.put({
                    "type": "credentials_login_result", "ok": True,
                    "email": email, "message": msg,
                })
            else:
                self.state = DriverState.ERROR
                self.log(f"Login failed: {msg}")
                self.result_queue.put({
                    "type": "credentials_login_result", "ok": False,
                    "email": email, "message": msg,
                })
                try:
                    await self._automation.cleanup()
                except Exception:
                    pass
        except Exception as e:
            self.state = DriverState.ERROR
            self.log(f"Credential login error: {e}")
            self.result_queue.put({
                "type": "credentials_login_result", "ok": False, "message": str(e),
            })
            try:
                await self._automation.cleanup()
            except Exception:
                pass

    # ── Auto Setup Profile ───────────────────────────────────

    async def _do_auto_setup(self, cmd: dict):
        """Run the full auto-setup flow for a profile (friends + profile + Pinterest)."""
        profile_name = cmd["profile_name"]
        target_friends = cmd.get("target_friends", 50)
        pinterest_query = cmd.get("pinterest_query")
        bio = cmd.get("bio")
        local_image_path = cmd.get("local_image_path")

        self.state = DriverState.STARTING
        self.log(f"Starting auto-setup for '{profile_name}'...")

        # Get the Brave profile path
        brave_path = cfg.get_profile_path(profile_name)
        if not brave_path:
            self.state = DriverState.ERROR
            self.result_queue.put({
                "type": "auto_setup_result", "ok": False,
                "profile_name": profile_name,
                "error": f"Profile '{profile_name}' has no Brave path",
            })
            return

        try:
            # Close existing browser if open
            if self._automation.context:
                self.log(f"Closing existing browser...")
                await self._automation.cleanup()
                await asyncio.sleep(1)

            # Launch the profile
            self.log(f"Launching profile '{profile_name}' for auto-setup...")
            await self._automation.start_browser_headless(brave_path)  # Background mode
            await self._automation.go_to_facebook()

            # Check if logged in
            logged_in = await self._automation._is_logged_in(timeout=15)
            if not logged_in:
                self.log("Profile not logged in - cannot auto-setup")
                self.state = DriverState.ERROR
                self.result_queue.put({
                    "type": "auto_setup_result", "ok": False,
                    "profile_name": profile_name,
                    "needs_login": True,
                    "error": "Profile is not logged in to Facebook",
                })
                await self._automation.cleanup()
                return

            # Step 1: Get the profile pic path (if needed)
            profile_pic_path = None
            images = None

            if local_image_path and os.path.isfile(local_image_path):
                self.log(f"  Using local image (skip Pinterest): {local_image_path}")
                profile_pic_path = local_image_path
            else:
                # Check profile setup first to see if we need a pic
                profile = await self._automation.check_profile_setup()
                needs_pic = not profile["has_profile_pic"]

                if needs_pic:
                    # NO FALLBACK TO AESTHETIC - User must provide pinterest_query
                    if not pinterest_query:
                        self.log(f"  ⚠️  No Pinterest query provided and profile needs picture")
                        self.log(f"  💡 For gender-based images, use 'Auto-setup ALL' instead")
                        self.log(f"  ⏭️  Skipping profile picture")
                        images = []
                    else:
                        self.log(f"  Scraping Pinterest for '{pinterest_query}'...")
                        images = await self._automation.scrape_pinterest_images(pinterest_query, count=10)
                        self.log(f"  Got {len(images)} Pinterest images")

                    if images:
                        # Send to UI for user preview
                        self.result_queue.put({
                            "type": "auto_setup_images_preview",
                            "profile_name": profile_name,
                            "images": images,
                            "needs_pic": needs_pic,
                        })

                        self.log("  Waiting for user to select images...")
                        self.state = DriverState.STOPPED
                        try:
                            response = await asyncio.get_event_loop().run_in_executor(
                                None, self._user_response_queue.get)
                        except Exception:
                            response = {"cancel": True}

                        if response.get("cancel"):
                            self.log("  User cancelled image selection, using first image")
                            profile_pic_path = images[0]
                        else:
                            profile_pic_path = response.get("profile_pic")

                        self.state = DriverState.STARTING
                    else:
                        self.log("  No Pinterest images downloaded - skipping photo setup")

            # Step 2: Run the full auto-setup (handles friends + pic + bio in one pass)
            self.log(f"  Running full auto-setup...")
            result = await self._automation.auto_setup_profile(
                target_friends=target_friends,
                bio=bio,
                profile_pic_path=profile_pic_path,
            )
            result["pinterest_images_downloaded"] = len(images) if images else 0

            self.state = DriverState.LOGGED_IN
            self.log(f"Auto-setup complete for '{profile_name}'")

            self.result_queue.put({
                "type": "auto_setup_result", "ok": True,
                "profile_name": profile_name,
                "result": result,
            })

        except Exception as e:
            self.state = DriverState.ERROR
            self.log(f"Auto-setup error: {e}")
            self.result_queue.put({
                "type": "auto_setup_result", "ok": False,
                "profile_name": profile_name,
                "error": str(e),
            })
        finally:
            try:
                await self._automation.cleanup()
            except Exception:
                pass

    async def _do_accept_all_pending(self, cmd: dict):
        """Check and accept pending friend requests on ALL profiles concurrently.
        
        This operation goes through every profile and accepts any pending friend requests
        from TWO sources:
        1. The official friend requests page (facebook.com/friends/requests)
        2. The followers page (profile?sk=followers) - where external users who sent requests appear
        
        This ensures all incoming friend requests are accepted, whether from other profiles
        in the system or from external Facebook users.
        """
        from src.storage import config_manager as cfg
        from src.core.facebook_automation import FacebookAutomation
        import asyncio
        
        self.log("=" * 60)
        self.log("📥 ACCEPTING PENDING FRIEND REQUESTS ON ALL PROFILES")
        self.log("=" * 60)
        self.log("Strategy: Check both Friend Requests page AND Followers page")
        all_profiles = cmd.get("profile_names") or cfg.list_profiles()
        self.log("Processing: Sequential (one profile at a time to prevent crashes)")
        self.log(f"Estimated time: {len(all_profiles) * 2}-{len(all_profiles) * 3} minutes")
        self.log("=" * 60)
        
        if not all_profiles:
            self.log("⚠️  No profiles found")
            return
        
        self.log(f"Found {len(all_profiles)} profile(s)")
        
        # Run SEQUENTIALLY (one at a time) to avoid browser crashes
        # Concurrent launches were causing exit code 21 errors
        MICRO_VIEWPORT = {"width": 400, "height": 600}
        _sem = asyncio.Semaphore(1)  # Changed from 3 to 1
        total_accepted = 0
        
        async def _accept_one(idx: int, profile_name: str) -> int:
            async with _sem:
                # Add stagger delay - longer for sequential processing
                await asyncio.sleep(idx * 2.0)  # Changed from 0.5 to 2.0 seconds
                
                brave_path = cfg.get_profile_path(profile_name)
                if not brave_path:
                    self.log(f"[{idx+1}/{len(all_profiles)}] ❌ '{profile_name}' - no profile path")
                    return 0
                
                accepted = 0
                automation = FacebookAutomation(log_callback=self.log, debug=self._debug)
                
                try:
                    self.log(f"[{idx+1}/{len(all_profiles)}] 🌐 Launching '{profile_name}'...")
                    await automation.start_browser_headless(
                        brave_path, kill_existing=False, viewport=MICRO_VIEWPORT
                    )
                    await automation.go_to_facebook()
                    
                    if not await automation._is_logged_in(timeout=10):
                        self.log(f"[{idx+1}/{len(all_profiles)}] ❌ '{profile_name}' - not logged in")
                        return 0
                    
                    # STRATEGY 1: Accept from official friend requests page
                    self.log(f"[{idx+1}/{len(all_profiles)}] 📥 Checking Friend Requests page...")
                    accepted_from_requests = await automation.auto_accept_friend_requests(max_accept=100)
                    accepted += accepted_from_requests
                    
                    if accepted_from_requests > 0:
                        self.log(f"[{idx+1}/{len(all_profiles)}]    ✅ Accepted {accepted_from_requests} from Requests page")
                    else:
                        self.log(f"[{idx+1}/{len(all_profiles)}]    ℹ️  No requests on Requests page")
                    
                    # STRATEGY 2: Check followers page for additional requests
                    self.log(f"[{idx+1}/{len(all_profiles)}] 👥 Checking Followers page...")
                    
                    # Get this profile's Facebook URL
                    my_url = await automation.get_my_profile_url()
                    if my_url:
                        self.log(f"[{idx+1}/{len(all_profiles)}]    Profile URL: {my_url}")
                        
                        # Accept requests from followers page
                        # Pass empty dict for all_profile_urls since we want to accept ALL followers
                        accepted_from_followers = await automation.accept_requests_from_followers_page(
                            my_profile_url=my_url,
                            all_profile_urls={}
                        )
                        accepted += accepted_from_followers
                        
                        if accepted_from_followers > 0:
                            self.log(f"[{idx+1}/{len(all_profiles)}]    ✅ Accepted {accepted_from_followers} from Followers page")
                        else:
                            self.log(f"[{idx+1}/{len(all_profiles)}]    ℹ️  No followers to accept")
                    else:
                        self.log(f"[{idx+1}/{len(all_profiles)}]    ⚠️  Could not get profile URL, skipping followers check")
                    
                    # Summary for this profile
                    if accepted > 0:
                        self.log(f"[{idx+1}/{len(all_profiles)}] ✅ '{profile_name}' - accepted {accepted} TOTAL request(s)")
                    else:
                        self.log(f"[{idx+1}/{len(all_profiles)}] ℹ️  '{profile_name}' - no pending requests")
                    
                except Exception as e:
                    self.log(f"[{idx+1}/{len(all_profiles)}] ❌ '{profile_name}' - error: {e}")
                    import traceback
                    self.log(f"   {traceback.format_exc()[:200]}")
                finally:
                    try:
                        await automation.cleanup()
                    except:
                        pass
                    
                    # Additional cleanup: wait a bit before next profile
                    await asyncio.sleep(2)
                    
                    # Force garbage collection to free memory
                    import gc
                    gc.collect()
                
                return accepted
        
        # Run all profiles concurrently
        tasks = [_accept_one(i, name) for i, name in enumerate(all_profiles)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count total accepted
        total_accepted = sum(r for r in results if isinstance(r, int))
        
        self.log("=" * 60)
        self.log(f"✅ FINISHED: Accepted {total_accepted} total friend request(s) across all profiles")
        self.log(f"💡 TIP: Click 'Check Friendship Status' to verify all profiles are friends")
        self.log("=" * 60)

    async def _do_check_login_status(self, cmd: dict):
        """Live-check which profiles are logged in to Facebook.

        Sequential per-profile extraction using the overlay-aware
        extract_storage_state().  Emits login_scan_progress per profile and
        a final login_scan_result with the full breakdown.
        """
        profiles = cmd.get("profile_names") or cfg.list_profiles()
        total = len(profiles)

        if not profiles:
            self.result_queue.put({
                "type": "login_scan_result", "ok": False,
                "results": [], "logged_in_count": 0, "total": 0,
                "error": "No saved profiles found",
            })
            return

        self.log(f"Checking login status for {total} profile(s)...")
        self.result_queue.put({
            "type": "login_scan_progress",
            "current": 0, "total": total,
            "message": f"Checking login status for {total} profile(s)...",
        })

        results: list[dict] = []
        for idx, profile_name in enumerate(profiles, 1):
            brave_path = cfg.get_profile_path(profile_name)
            if not brave_path:
                results.append({"profile_name": profile_name, "logged_in": False,
                                "reason": "no Brave path"})
                self.result_queue.put({
                    "type": "login_scan_progress",
                    "current": idx, "total": total,
                    "profile_name": profile_name, "logged_in": False,
                    "message": f"[{idx}/{total}] '{profile_name}' — no Brave path",
                })
                continue

            self.log(f"[{idx}/{total}] Extracting '{profile_name}'...")
            temp_auto = self._create_temp_automation()
            try:
                state, logged_in = await temp_auto.extract_storage_state(
                    brave_path, return_logged_in=True)
                if state is None:
                    results.append({"profile_name": profile_name, "logged_in": False,
                                    "reason": "could not extract session"})
                    self.result_queue.put({
                        "type": "login_scan_progress",
                        "current": idx, "total": total,
                        "profile_name": profile_name, "logged_in": False,
                        "message": f"[{idx}/{total}] '{profile_name}' — could not extract session",
                    })
                else:
                    # Persist what the scan learned, so the login count and
                    # the next queue run start from it instead of from zero.
                    from src.storage import state_cache
                    if logged_in:
                        state_cache.save_state(profile_name, state)
                    else:
                        state_cache.invalidate(profile_name)
                    reason = "logged_in" if logged_in else getattr(
                        temp_auto, "last_account_status", "unknown_not_logged_in")
                    # The verdict is what "active" means everywhere else
                    # (status 'ok'), so record it on the linked account.
                    await self._record_and_publish(profile_name, logged_in,
                                                   reason)
                    removed = False
                    if reason == "disabled_or_suspended":
                        # Remove only the app's saved reference. The underlying
                        # Brave profile directory is intentionally preserved.
                        removed = cfg.delete_profile(profile_name)
                        if removed:
                            self.log(f"  🗑 Auto-removed disabled Facebook profile '{profile_name}' from the app")
                    results.append({"profile_name": profile_name, "logged_in": logged_in,
                                    "reason": reason, "removed": removed})
                    status = "✅ logged in" if logged_in else f"❌ {reason.replace('_', ' ')}"
                    if removed:
                        status += " — auto-removed"
                    self.result_queue.put({
                        "type": "login_scan_progress",
                        "current": idx, "total": total,
                        "profile_name": profile_name, "logged_in": logged_in,
                        "message": f"[{idx}/{total}] '{profile_name}' — {status}",
                    })
            except Exception as e:
                self.log(f"  ❌ Failed to check '{profile_name}': {e}")
                results.append({"profile_name": profile_name, "logged_in": False,
                                "reason": str(e)})
                self.result_queue.put({
                    "type": "login_scan_progress",
                    "current": idx, "total": total,
                    "profile_name": profile_name, "logged_in": False,
                    "message": f"[{idx}/{total}] '{profile_name}' — check failed: {e}",
                })

            if idx < total:
                pause = random.uniform(2.0, 4.0)
                self.log(f"  ⏳ Pausing {pause:.1f}s before next profile...")
                await asyncio.sleep(pause)

        logged_in_count = sum(1 for r in results if r.get("logged_in"))
        removed_profiles = [r["profile_name"] for r in results if r.get("removed")]
        self.result_queue.put({
            "type": "login_scan_result", "ok": True,
            "results": results,
            "logged_in_count": logged_in_count,
            "total": total,
            "removed_profiles": removed_profiles,
        })
        self.log(f"Login check done — {logged_in_count}/{total} logged in")

    @staticmethod
    def _brave_running() -> bool:
        """Any brave.exe holds Chromium's singleton lock on the shared
        User Data dir, so a login inside a real profile cannot launch.
        The same check scripts/login_accounts.py makes before it starts."""
        try:
            import psutil
            return any((p.info.get("name") or "").lower() == "brave.exe"
                       for p in psutil.process_iter(["name"]))
        except Exception:
            return False

    async def _batch_pause(self, seconds: float) -> None:
        """The rest between login batches. Its own method so a proof can watch
        it without waiting minutes."""
        await asyncio.sleep(0 if getattr(self, "_fast_tests", False) else seconds)

    async def _do_login_accounts(self, cmd: dict):
        """Log roster accounts in from the GUI.

        Sequential by necessity (Brave's singleton lock), inside each
        account's real profile so the session cookies stay decryptable.
        Per account: LOGGING IN on the sheet, _relogin_profile() (which
        records the verdict and pushes it), a short pause.
        """
        usernames = [u for u in (cmd.get("usernames") or []) if u]
        total = len(usernames)

        def finish(**kw):
            base = {"type": "login_accounts_result", "total": total,
                    "logged_in": [], "failed": [], "skipped": []}
            base.update(kw)
            self.result_queue.put(base)

        if not usernames:
            finish(ok=False, error="No accounts to log in")
            return
        if self._batch_running or self._watch_autos:
            finish(ok=False, error="A run or watch is active - wait for it "
                                   "to finish, then try again")
            return
        if self._brave_running():
            finish(ok=False, error="Brave is open and locks the shared profile "
                                   "directory. Close every Brave window, then "
                                   "try again.")
            return

        from src.storage import sheet_status
        by_user = {(a.get("username") or "").strip().lower(): a
                   for a in db.list_accounts()}
        writer = await asyncio.to_thread(sheet_status.SheetWriter)
        if not writer.on:
            self.log(f"  ⚠️  live sheet updates off: "
                     f"{sheet_reason(Exception(writer.error))}")
        # A batch is the burst that runs before a pause. Sequentially that is
        # LOGIN_BATCH_SIZE logins; in a parallel wave the wave itself is the
        # burst, so the default batch is the wave width.
        default_batch = (self.LOGIN_PARALLEL if browser_choice.supports_parallel_login()
                         else self.LOGIN_BATCH_SIZE)
        batch_size = int(cmd.get("batch_size", default_batch) or 0)
        pause_minutes = float(cmd.get("pause_minutes", self.LOGIN_BATCH_PAUSE_MIN) or 0)
        self.log(f"Logging in {total} account(s)..."
                 + (f" in batches of {batch_size}, {pause_minutes:g} min apart"
                    if batch_size and total > batch_size else ""))
        logged_in, failed, skipped = [], [], []

        # Flagged as a run for as long as it lasts: the session sweep skips a
        # pass while one is active, and a sweep re-login landing mid-run would
        # open a second persistent context on the same locked User Data dir.
        self._batch_running = True

        async def _login_one(idx: int, username: str):
            """One account, start to definitive verdict: logged in, disabled,
            gated, or a stated failure. Returns nothing; it files its own
            result and emits its own progress line."""
            nonlocal logged_in, failed, skipped
            if True:
                acct = by_user.get(username.strip().lower())
                profile = (acct or {}).get("linked_profile") or ""
                reason = ""
                ok = False
                if acct is None:
                    reason = "not in roster"
                    skipped.append((username, reason))
                elif acct.get("status") == "disabled":
                    reason = "disabled"
                    skipped.append((username, reason))
                elif (acct.get("status") == "ok"
                      or (acct.get("sheet_status") or "").strip().upper() == "LOGGED IN"):
                    # Already signed in. Opening a browser for it costs a
                    # minute and risks drawing a fresh checkpoint on a session
                    # that was working. Note the exact match: "NOT LOGGED IN"
                    # contains the same two words and must still be attempted.
                    reason = "already logged in"
                    skipped.append((username, reason))
                elif not profile:
                    reason = "no Brave profile - run scripts/provision_profiles.py"
                    skipped.append((username, reason))
                elif not cfg.get_profile_path(profile):
                    # The roster points at a profile this machine never saved
                    # (a hand-entered link, or one removed from Brave). Opening
                    # nothing is a skip, not a failed login attempt.
                    reason = f"Brave profile '{profile}' is not registered on this PC"
                    skipped.append((username, reason))
                else:
                    if writer.on:
                        await asyncio.to_thread(writer.mark_in_progress, username)
                    # The grid is sized for the windows actually open: a run
                    # of five tiles 3x2, not five cells of a 5x5 grid with
                    # twenty empty ones.
                    width = max(1, min(int(self.LOGIN_PARALLEL), total,
                                       batch_size or int(self.LOGIN_PARALLEL)))
                    ok = await self._relogin_profile(
                        profile, why="Login requested",
                        slot=(idx - 1) % width, wave=width)
                    after = db.account_for_profile(profile) or {}
                    reason = ("logged in" if ok else
                              (after.get("status_reason")
                               or "could not log in - see log"))
                    (logged_in if ok else failed).append((username, reason))
                self.result_queue.put({
                    "type": "login_accounts_progress",
                    "current": idx, "total": total,
                    "username": username, "profile_name": profile, "ok": ok,
                    "message": f"[{idx}/{total}] {username}: {reason}",
                })

        jobs = list(enumerate(usernames, 1))
        try:
            if browser_choice.supports_parallel_login():
                # Chromium: a directory per account, so nothing is shared and a
                # wave can run together. Waves, not a rolling pool, because each
                # account must reach a definitive verdict - logged in, disabled,
                # needs an authenticator - before the next wave starts.
                # Never run more at once than one batch: batch_size is what
                # spaces the run, so a wave that outran it would skip the pause.
                width = max(1, min(int(self.LOGIN_PARALLEL), total,
                                   batch_size or int(self.LOGIN_PARALLEL)))
                self.log(f"  Chromium: logging in {width} at a time")
                for start in range(0, len(jobs), width):
                    wave = jobs[start:start + width]
                    await asyncio.gather(*(_login_one(i, u) for i, u in wave))
                    # batch_size 0 means one unbroken run, waves included.
                    if batch_size and start + width < len(jobs):
                        self.log(f"  Wave of {len(wave)} done - pausing "
                                 f"{pause_minutes:g} min "
                                 f"({min(start + width, len(jobs))}/{total} attempted)")
                        await self._batch_pause(pause_minutes * 60.0)
            else:
                # Brave: one at a time, and that is not a tuning choice. Its
                # cookie key is bound to the shared User Data directory that
                # Chromium's ProcessSingleton locks.
                for idx, username in jobs:
                    await _login_one(idx, username)
                    if idx < total:
                        await asyncio.sleep(0 if getattr(self, "_fast_tests", False)
                                            else random.uniform(2.0, 4.0))
                    if batch_size and idx < total and idx % batch_size == 0:
                        self.log(f"  Batch of {batch_size} done - pausing "
                                 f"{pause_minutes:g} min ({idx}/{total} attempted)")
                        await self._batch_pause(pause_minutes * 60.0)
        finally:
            self._batch_running = False

        finish(ok=True, logged_in=logged_in, failed=failed, skipped=skipped)

    async def _do_auto_setup_all(self, cmd: dict):
        """Run auto-setup on every saved Brave profile sequentially.

        Iterates through all profiles, running the same logic as
        _do_auto_setup() for each one.  Sends per-profile progress
        results and a final summary.
        
        After all profiles are set up, connects them by:
        1. Getting each profile's Facebook URL
        2. Having each profile send friend requests to all others
        3. Having each profile accept pending friend requests
        """
        target_friends = cmd.get("target_friends", 50)
        pinterest_query = cmd.get("pinterest_query")
        bio = cmd.get("bio")
        connect_friends = cmd.get("connect_friends", True)

        from src.storage import database as db
        from src.core.facebook_automation import FacebookAutomation

        profiles = cmd.get("profile_names") or cfg.list_profiles()
        total = len(profiles)

        # Override target_friends to match the number of managed profiles
        # Each profile should only be friends with the other managed profiles, not random people
        if total >= 2:
            target_friends = total - 1
        self.log(f"Auto-setup ALL: {total} profile(s) — target={target_friends} friends (each profile friends with {target_friends} others)")

        if not profiles:
            self.result_queue.put({
                "type": "auto_setup_all_result", "ok": False,
                "error": "No saved profiles found",
            })
            return

        self.result_queue.put({
            "type": "auto_setup_all_progress",
            "current": 0, "total": total,
            "profile_name": "", "ok": True,
            "message": f"✅ Starting auto-setup for {total} profile(s)...",
        })

        results: list[dict] = []
        success_count = 0
        profile_facebook_urls: dict[str, str] = {}  # Store Facebook URLs for cross-friending
        profiles_analysis_data: list[dict] = []  # Data for Groq AI analysis
        connection_analysis_data: list[dict] = []  # Connection results for Groq AI analysis
        
        # ── PRE-SCAN: Count male/female profiles to download exact number of images ──────
        self.log(f"\n🔍 Pre-scanning profiles to detect gender distribution...")
        
        male_count = 0
        female_count = 0
        unknown_count = 0
        profile_genders: dict[str, str] = {}  # Cache gender detection results
        
        # Quick scan through profiles to count genders (use profile names as proxy)
        for profile_name in profiles:
            # Use Brave profile name as initial guess (will be updated with Facebook name later)
            detected_gender = self._detect_gender_from_name(profile_name)
            profile_genders[profile_name] = detected_gender
            
            if detected_gender == "male":
                male_count += 1
            elif detected_gender == "female":
                female_count += 1
            else:
                unknown_count += 1
        
        self.log(f"   📊 Gender distribution (based on profile names):")
        self.log(f"      👨 Male profiles: {male_count}")
        self.log(f"      👩 Female profiles: {female_count}")
        self.log(f"      ⚪ Unknown gender: {unknown_count}")
        
        # ALWAYS download 20 images for each gender (regardless of profile count)
        # This builds a library of diverse images
        male_image_count = 20 if (male_count > 0 or unknown_count > 0) else 0
        female_image_count = 20 if (female_count > 0 or unknown_count > 0) else 0
        
        self.log(f"   📦 Will download: {male_image_count} male images, {female_image_count} female images")
        self.log(f"   💡 Always downloading 20 per gender to build image library")
        
        # ── Download Pinterest images ONCE (before processing profiles) ──────
        pinterest_images: list[str] = []
        used_images: set[str] = set()  # Track which images have been used (in-memory + DB)
        
        # Load previously used images from database so we never reuse across runs
        previously_used = db.get_used_image_paths()
        used_images.update(previously_used)
        if previously_used:
            self.log(f"   📋 Loaded {len(previously_used)} previously used image(s) from database")
        
        # Gender-based image storage
        male_images: list[str] = []
        female_images: list[str] = []
        
        if male_image_count > 0 or female_image_count > 0:
            self.log(f"\n📥 Downloading Pinterest images...")
            
            # Create temporary automation just for Pinterest scraping
            temp_auto = FacebookAutomation(log_callback=self.log, debug=self._debug)
            
            try:
                # Launch a minimal browser just for Pinterest (headless)
                import tempfile
                
                # Create PERMANENT folders for male and female images (not in temp)
                # This ensures images are saved as backup and not deleted
                import os
                
                # Save to a permanent location in user's Documents or app directory
                # Option 1: User's Documents folder
                documents_path = os.path.expanduser("~/Documents")
                permanent_storage = os.path.join(documents_path, "FB_Automation_Images")
                
                # Option 2: Next to the application (fallback if Documents not accessible)
                if not os.path.exists(documents_path):
                    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    permanent_storage = os.path.join(app_dir, "saved_images")
                
                # Create timestamped folder for this download session
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                base_permanent_dir = os.path.join(permanent_storage, f"session_{timestamp}")
                male_images_dir = os.path.join(base_permanent_dir, "pinoy_male")
                female_images_dir = os.path.join(base_permanent_dir, "pinay_female")
                
                os.makedirs(male_images_dir, exist_ok=True)
                os.makedirs(female_images_dir, exist_ok=True)
                
                # Also create a temp profile for Pinterest browser (separate from images)
                temp_profile = os.path.join(tempfile.gettempdir(), f"pinterest_browser_{int(time.time())}")
                
                self.log(f"   Opening browser for Pinterest...")
                self.log(f"   💾 PERMANENT STORAGE: {base_permanent_dir}")
                self.log(f"   📁 Male images folder: {male_images_dir}")
                self.log(f"   📁 Female images folder: {female_images_dir}")
                self.log(f"   ℹ️  Images will be saved permanently for backup!")
                await temp_auto.start_browser_headless(temp_profile)
                
                # Download PINOY (male) images - only if needed
                if male_image_count > 0:
                    self.log(f"   📦 Downloading {male_image_count} PINOY (male) images...")
                    
                    # Try multiple search queries to get enough images
                    # Strategy: Start with generic terms (more results), then specific
                    male_queries = [
                        "man portrait photo",              # Very generic, lots of results
                        "male profile picture",            # Generic
                        "asian man photo",                 # Broader than Filipino-specific
                        "filipino man",                    # More specific
                        "man headshot",                    # Professional photos
                    ]
                    
                    for query_idx, male_query in enumerate(male_queries):
                        if len(male_images) >= male_image_count:
                            break  # Got enough images
                            
                        remaining = male_image_count - len(male_images)
                        self.log(f"   🔍 Male search {query_idx + 1}/{len(male_queries)}: '{male_query}' (need {remaining} more)")
                        
                        try:
                            batch = await temp_auto.scrape_pinterest_images(male_query, count=remaining, save_dir=male_images_dir)
                            male_images.extend(batch)
                            self.log(f"      ✅ Got {len(batch)} images from '{male_query}' (total: {len(male_images)})")
                        except Exception as e:
                            self.log(f"      ⚠️  Pinterest error for '{male_query}': {e}")
                    
                    self.log(f"   ✅ Downloaded {len(male_images)} pinoy images to: {male_images_dir}")
                else:
                    self.log(f"   ⏭️  Skipping male images (no male profiles detected)")
                
                # Download PINAY (female) images - only if needed
                # Download PINAY (female) images - only if needed
                if female_image_count > 0:
                    self.log(f"   📦 Downloading {female_image_count} PINAY (female) images...")
                    
                    # Try multiple search queries to get enough images
                    # Strategy: Start with generic terms (more results), then specific
                    female_queries = [
                        "woman portrait photo",            # Very generic, lots of results
                        "female profile picture",          # Generic
                        "asian woman photo",               # Broader than Filipino-specific
                        "filipina woman",                  # More specific
                        "woman headshot",                  # Professional photos
                    ]
                    
                    for query_idx, female_query in enumerate(female_queries):
                        if len(female_images) >= female_image_count:
                            break  # Got enough images
                            
                        remaining = female_image_count - len(female_images)
                        self.log(f"   🔍 Female search {query_idx + 1}/{len(female_queries)}: '{female_query}' (need {remaining} more)")
                        
                        try:
                            batch = await temp_auto.scrape_pinterest_images(female_query, count=remaining, save_dir=female_images_dir)
                            female_images.extend(batch)
                            self.log(f"      ✅ Got {len(batch)} images from '{female_query}' (total: {len(female_images)})")
                        except Exception as e:
                            self.log(f"      ⚠️  Pinterest error for '{female_query}': {e}")
                        
                    self.log(f"   ✅ Downloaded {len(female_images)} pinay images to: {female_images_dir}")
                else:
                    self.log(f"   ⏭️  Skipping female images (no female profiles detected)")
                
                # Combine all images for fallback
                pinterest_images = male_images + female_images
                
                self.log(f"   ✅ Total: {len(pinterest_images)} images ({len(male_images)} pinoy, {len(female_images)} pinay)")
                self.log(f"   💾 Images saved permanently to: {base_permanent_dir}")
                self.log(f"   🔄 You can reuse these images for future auto-setup runs!")
                
                if len(pinterest_images) == 0:
                    self.log(f"   ❌ NO IMAGES DOWNLOADED - Pinterest may be blocked or timing out")
                    self.log(f"   💡 TIP: You can manually place images in folders and run setup again")
                    self.log(f"   💡 Or run auto-setup without profile pictures (will only add friends)")
                elif len(male_images) < male_count:
                    self.log(f"   ⚠️  Only {len(male_images)} male images for {male_count} male profiles - may reuse")
                elif len(female_images) < female_count:
                    self.log(f"   ⚠️  Only {len(female_images)} female images for {female_count} female profiles - may reuse")
                
            except Exception as e:
                self.log(f"   ❌ Pinterest download failed: {e}")
                self.log(f"   ⚠️  Will skip profile picture setup for all profiles")
            finally:
                try:
                    await temp_auto.cleanup()
                except:
                    pass
        else:
            self.log(f"\n⏭️  No profile pictures needed - skipping Pinterest download")
        
        # ── CONCURRENT PROFILE PROCESSING ──────────────────────────────
        # All profiles run simultaneously with tiny viewports
        MAX_CONCURRENT = 2  # Run up to 2 profiles at a time to avoid browser crashes
        _sem = asyncio.Semaphore(MAX_CONCURRENT)
        success_count = 0  # Initialize success counter
        
        self.log(f"\n🚀 Launching all {total} profiles CONCURRENTLY (max {MAX_CONCURRENT} at a time, micro viewport)")
        
        async def _setup_one(idx: int, profile_name: str) -> dict:
            """Set up a single profile — runs concurrently with others."""
            nonlocal success_count  # Allow modification of outer scope variable
            async with _sem:
                # Add small stagger delay to prevent all profiles launching at exact same time
                # This helps avoid race conditions with profile directory locks
                await asyncio.sleep(idx * 0.5)  # 0.5s delay per profile
                
                result_entry = {"ok": False, "profile_name": profile_name, "error": ""}
                brave_path = cfg.get_profile_path(profile_name)
                if not brave_path:
                    msg = f"No Brave path"
                    self.log(f"  [{idx+1}/{total}] ❌ '{profile_name}' — {msg}")
                    result_entry["error"] = msg
                    self.result_queue.put({
                        "type": "auto_setup_all_progress",
                        "current": idx + 1, "total": total,
                        "profile_name": profile_name, "ok": False, "message": msg,
                    })
                    return result_entry

                automation = FacebookAutomation(log_callback=self.log, debug=self._debug)
                try:
                    # Kill existing=FALSE for concurrent — never kill other profiles' browsers
                    self.log(f"  [{idx+1}/{total}] 🌐 Launching '{profile_name}' (micro viewport)...")
                    await automation.start_browser_headless(
                        brave_path, kill_existing=False, viewport=MICRO_VIEWPORT
                    )
                    await automation.go_to_facebook()

                    if not await automation._is_logged_in(timeout=15):
                        msg = f"Not logged in"
                        self.log(f"  [{idx+1}/{total}] ❌ '{profile_name}' — {msg}")
                        result_entry["error"] = msg
                        self.result_queue.put({
                            "type": "auto_setup_all_progress",
                            "current": idx + 1, "total": total,
                            "profile_name": profile_name, "ok": False, "message": msg, "needs_login": True,
                        })
                        return result_entry

                    # Get Facebook URL
                    fb_url = await automation.get_my_profile_url()
                    if fb_url:
                        profile_facebook_urls[profile_name] = fb_url
                        cfg.save_facebook_url(profile_name, fb_url)
                        self.log(f"  [{idx+1}/{total}] ✅ '{profile_name}' URL: {fb_url}")

                    # Get Facebook name for gender detection
                    fb_name = await automation.get_my_profile_name()
                    if fb_name and fb_name.lower() not in ['facebook', 'home', 'profile']:
                        self.log(f"  [{idx+1}/{total}] 📛 '{profile_name}' name: {fb_name}")
                    else:
                        fb_name = profile_name

                    # Check if profile already has a picture
                    profile_status = await automation.check_profile_setup()
                    already_has_picture = profile_status.get("has_profile_pic", False)

                    # Assign unique image (only if needed)
                    profile_pic_path = None
                    if pinterest_images and not already_has_picture:
                        profile_gender = self._detect_gender_from_name(fb_name)
                        if profile_gender == "male" and male_images:
                            available = [img for img in male_images if img not in used_images]
                            if available:
                                profile_pic_path = available[0]
                        elif profile_gender == "female" and female_images:
                            available = [img for img in female_images if img not in used_images]
                            if available:
                                profile_pic_path = available[0]
                        elif not (profile_gender in ("male", "female")):
                            available = [img for img in pinterest_images if img not in used_images]
                            if available:
                                profile_pic_path = available[0]

                        if profile_pic_path and os.path.isfile(profile_pic_path):
                            used_images.add(profile_pic_path)
                            db.mark_image_used(profile_pic_path, profile_name)
                            self.log(f"  [{idx+1}/{total}] 🖼️  '{profile_name}' assigned: {os.path.basename(profile_pic_path)}")
                        else:
                            profile_pic_path = None

                    # Run auto-setup
                    self.log(f"  [{idx+1}/{total}] ⚙️  Running setup for '{profile_name}'...")
                    setup_result = await automation.auto_setup_profile(
                        target_friends=target_friends,
                        pinterest_query=None,
                        bio=None,
                        connect_friends=False,
                        profile_pic_path=profile_pic_path,
                    )

                    result_entry["ok"] = True
                    result_entry["result"] = setup_result
                    success_count += 1

                    # Collect analysis data
                    profile_gender = self._detect_gender_from_name(fb_name)
                    friend_count = await automation.check_friends_count()
                    profiles_analysis_data.append({
                        "profile_name": profile_name,
                        "facebook_url": profile_facebook_urls.get(profile_name, "N/A"),
                        "gender": profile_gender,
                        "friend_count": friend_count,
                        "friends_added": setup_result.get("friends_added", 0),
                    })

                    self.log(f"  [{idx+1}/{total}] ✅ '{profile_name}' done: +{setup_result.get('friends_added', 0)} friends")
                    self.result_queue.put({
                        "type": "auto_setup_all_progress",
                        "current": idx + 1, "total": total,
                        "profile_name": profile_name, "ok": True,
                        "message": f"{profile_name}: +{setup_result.get('friends_added', 0)} friends, pic={'✅' if setup_result.get('profile_pic_set') or setup_result.get('had_profile_pic') else '❌'}",
                    })

                except Exception as e:
                    msg = f"Error: {e}"
                    self.log(f"  [{idx+1}/{total}] ❌ '{profile_name}' — {msg}")
                    result_entry["error"] = str(e)
                    self.result_queue.put({
                        "type": "auto_setup_all_progress",
                        "current": idx + 1, "total": total,
                        "profile_name": profile_name, "ok": False, "message": msg,
                    })
                finally:
                    try:
                        await automation.cleanup()
                    except Exception:
                        pass

                return result_entry

        # ── Launch all profile setups concurrently ─────────────
        setup_tasks = [_setup_one(idx, name) for idx, name in enumerate(profiles)]
        setup_results = await asyncio.gather(*setup_tasks, return_exceptions=True)

        for r in setup_results:
            if isinstance(r, Exception):
                self.log(f"  ❌ Task exception: {r}")
            elif isinstance(r, dict):
                results.append(r)

        self.log(f"\n✅ Profile setup phase complete: {success_count}/{total} successful")

        profile_names = list(profile_facebook_urls.keys())

        # ── CONCURRENT FRIEND CONNECTIONS ──────────────────────
        if not connect_friends:
            self.log(f"\nℹ️  Friend connection DISABLED — skipping")
        elif len(profile_facebook_urls) >= 2:
            self.log(f"\n{'='*50}")
            self.log(f"🤝 CONCURRENT Friend Connections ({len(profile_facebook_urls)} profiles)")
            self.log(f"{'='*50}")

            profile_names = list(profile_facebook_urls.keys())
            total_pairs = len(profile_names) * (len(profile_names) - 1) // 2

            self.result_queue.put({
                "type": "auto_setup_all_progress",
                "current": total, "total": total,
                "profile_name": "", "ok": True,
                "message": f"🤝 Connecting {len(profile_facebook_urls)} profiles...",
            })

            # ── PASS 1: All profiles SEND requests concurrently ──────
            self.log(f"\n{'='*50}")
            self.log(f"📤 PASS 1/3: Sending friend requests (CONCURRENT)")
            self.log(f"{'='*50}")

            async def _send_one(idx: int, sender_name: str) -> int:
                async with _sem:
                    # Add small stagger delay to prevent simultaneous launches
                    await asyncio.sleep(idx * 0.5)
                    
                    sent_count = 0
                    brave_path = cfg.get_profile_path(sender_name)
                    if not brave_path:
                        return 0

                    automation = FacebookAutomation(log_callback=self.log, debug=self._debug)
                    try:
                        await automation.start_browser_headless(
                            brave_path, kill_existing=False, viewport=MICRO_VIEWPORT
                        )
                        await automation.go_to_facebook()
                        if not await automation._is_logged_in(timeout=10):
                            return 0

                        for target_name, target_url in profile_facebook_urls.items():
                            if target_name == sender_name:
                                continue
                            if db.are_friends(sender_name, target_name):
                                continue

                            status = await automation.send_friend_request_to_profile(target_url)
                            if status == "sent":
                                sent_count += 1
                                db.record_friend_sent(sender_name, target_name)
                            elif status == "accepted":
                                db.record_friend_accepted(sender_name, target_name)
                            elif status == "already_friends":
                                db.record_friend_accepted(sender_name, target_name)
                            elif status == "pending":
                                db.record_friend_sent(sender_name, target_name)
                            connection_analysis_data.append({
                                "sender": sender_name, "target": target_name,
                                "action": "send_request", "success": status in ("sent", "accepted"), "detail": f"pass 1 ({status})",
                            })
                            await asyncio.sleep(1)

                        self.log(f"  [{idx+1}/{len(profile_names)}] '{sender_name}' sent {sent_count} requests")
                    except Exception as e:
                        self.log(f"  [{idx+1}/{len(profile_names)}] '{sender_name}' error: {e}")
                    finally:
                        try:
                            await automation.cleanup()
                        except:
                            pass
                    return sent_count

            send_tasks = [_send_one(i, name) for i, name in enumerate(profile_names)]
            send_results = await asyncio.gather(*send_tasks, return_exceptions=True)
            total_sent = sum(r for r in send_results if isinstance(r, int))
            self.log(f"\n📤 Pass 1 done: {total_sent} requests sent")

            # Wait for Facebook to process friend requests before accepting
            wait_seconds = 20
            self.log(f"\n⏳ Waiting {wait_seconds}s for Facebook to process requests...")
            await asyncio.sleep(wait_seconds)

            # ── PASS 2: All profiles ACCEPT concurrently ──────
            self.log(f"\n{'='*50}")
            self.log(f"📥 PASS 2/3: Accepting friend requests (CONCURRENT)")
            self.log(f"{'='*50}")

            async def _accept_one(idx: int, profile_name: str) -> int:
                async with _sem:
                    # Add small stagger delay to prevent simultaneous launches
                    await asyncio.sleep(idx * 0.5)
                    
                    accepted = 0
                    brave_path = cfg.get_profile_path(profile_name)
                    if not brave_path:
                        return 0

                    automation = FacebookAutomation(log_callback=self.log, debug=self._debug)
                    try:
                        await automation.start_browser_headless(
                            brave_path, kill_existing=False, viewport=MICRO_VIEWPORT
                        )
                        await automation.go_to_facebook()
                        if not await automation._is_logged_in(timeout=10):
                            return 0

                        # METHOD 1: Friend requests page (most reliable for incoming requests)
                        self.log(f"  [{idx+1}/{len(profile_names)}] '{profile_name}' — checking friend-requests page...")
                        requests_accepted = await automation.auto_accept_friend_requests(max_accept=50)
                        accepted += requests_accepted

                        # METHOD 2: Also try inbox-style accept as backup
                        if accepted == 0:
                            inbox_accepted = await automation.accept_friend_requests_from_inbox(max_accept=50)
                            accepted += inbox_accepted

                        # METHOD 3: Visit each other profile's page (backup for confirm buttons on profiles)
                        other_urls = {name: url for name, url in profile_facebook_urls.items()
                                      if name != profile_name}
                        confirmed_list = await automation.accept_friend_requests_by_visiting_profiles(other_urls)

                        # Record ONLY the specific profiles that were confirmed
                        for confirmed_name in confirmed_list:
                            if confirmed_name in profile_names and not db.are_friends(profile_name, confirmed_name):
                                db.record_friend_accepted(profile_name, confirmed_name)
                                accepted += 1
                                connection_analysis_data.append({
                                    "sender": profile_name, "target": confirmed_name,
                                    "action": "accept_request", "success": True, "detail": "pass 2",
                                })

                        self.log(f"  [{idx+1}/{len(profile_names)}] '{profile_name}' accepted {accepted}")
                    except Exception as e:
                        self.log(f"  [{idx+1}/{len(profile_names)}] '{profile_name}' error: {e}")
                    finally:
                        try:
                            await automation.cleanup()
                        except:
                            pass
                    return accepted

            accept_tasks = [_accept_one(i, name) for i, name in enumerate(profile_names)]
            accept_results = await asyncio.gather(*accept_tasks, return_exceptions=True)
            total_accepted = sum(r for r in accept_results if isinstance(r, int))
            self.log(f"\n📥 Pass 2 done: {total_accepted} requests accepted")

            # ── PASS 3: REPAIR any remaining non-friends ──────
            friends_count = sum(
                1 for i, a in enumerate(profile_names)
                for b in profile_names[i + 1:]
                if db.are_friends(a, b)
            )
            if friends_count < total_pairs:
                self.log(f"\n{'='*50}")
                self.log(f"🔧 PASS 3/3: Repairing {total_pairs - friends_count} remaining non-friend pairs")
                self.log(f"{'='*50}")

                async def _repair_one(idx: int, profile_name: str) -> int:
                    async with _sem:
                        # Add small stagger delay to prevent simultaneous launches
                        await asyncio.sleep(idx * 0.5)
                        
                        non_friends = db.get_non_friends(profile_name, profile_names)
                        if not non_friends:
                            return 0

                        brave_path = cfg.get_profile_path(profile_name)
                        if not brave_path:
                            return 0

                        accepted = 0
                        automation = FacebookAutomation(log_callback=self.log, debug=self._debug)
                        try:
                            await automation.start_browser_headless(
                                brave_path, kill_existing=False, viewport=MICRO_VIEWPORT
                            )
                            await automation.go_to_facebook()
                            if not await automation._is_logged_in(timeout=10):
                                return 0

                            # Send to non-friends
                            for other_name in non_friends:
                                other_url = profile_facebook_urls.get(other_name)
                                if other_url:
                                    status = await automation.send_friend_request_to_profile(other_url)
                                    if status == "sent":
                                        db.record_friend_sent(profile_name, other_name)
                                    elif status in ("accepted", "already_friends"):
                                        db.record_friend_accepted(profile_name, other_name)
                                    elif status == "pending":
                                        db.record_friend_sent(profile_name, other_name)
                                    await asyncio.sleep(1)

                            # Accept via friend requests page
                            requests_accepted = await automation.auto_accept_friend_requests(max_accept=50)
                            accepted += requests_accepted

                            # Also try inbox as backup
                            if accepted == 0:
                                inbox_accepted = await automation.accept_friend_requests_from_inbox(max_accept=50)
                                accepted += inbox_accepted

                            # Also try visiting each sender's profile
                            other_urls = {name: url for name, url in profile_facebook_urls.items()
                                          if name != profile_name}
                            confirmed_list = await automation.accept_friend_requests_by_visiting_profiles(other_urls)
                            for confirmed_name in confirmed_list:
                                if confirmed_name in profile_names and not db.are_friends(profile_name, confirmed_name):
                                    db.record_friend_accepted(profile_name, confirmed_name)
                                    accepted += 1

                            self.log(f"  [{idx+1}/{len(profile_names)}] '{profile_name}' repaired {accepted}")
                        except Exception as e:
                            self.log(f"  [{idx+1}/{len(profile_names)}] '{profile_name}' error: {e}")
                        finally:
                            try:
                                await automation.cleanup()
                            except:
                                pass
                        return accepted

                repair_tasks = [_repair_one(i, name) for i, name in enumerate(profile_names)]
                await asyncio.gather(*repair_tasks, return_exceptions=True)

            # Final friends count
            friends_count = sum(
                1 for i, a in enumerate(profile_names)
                for b in profile_names[i + 1:]
                if db.are_friends(a, b)
            )
            self.log(f"\n{'='*50}")
            self.log(f"🤝 Friend connection complete!")
            self.log(f"   Sent: {total_sent} | Accepted: {total_accepted}")
            self.log(f"   Network: {friends_count}/{total_pairs} pairs are friends")
            self.log(f"{'='*50}")

            # ── VERIFY + FORCED REPAIR LOOP ─────────────────────
            # If not all profiles are friends, keep trying until they are
            expected_pairs = total_pairs
            MAX_REPAIR_ROUNDS = 5
            repair_round = 0

            while friends_count < expected_pairs and repair_round < MAX_REPAIR_ROUNDS:
                repair_round += 1
                missing_pairs = expected_pairs - friends_count
                self.log(f"\n{'='*50}")
                self.log(f"🔧 FORCED REPAIR ROUND {repair_round}/{MAX_REPAIR_ROUNDS}: {missing_pairs} pairs still not connected")
                self.log(f"{'='*50}")

                async def _force_repair_one(idx: int, profile_name: str) -> int:
                    async with _sem:
                        # Add small stagger delay to prevent simultaneous launches
                        await asyncio.sleep(idx * 0.5)
                        
                        non_friends = db.get_non_friends(profile_name, profile_names)
                        if not non_friends:
                            return 0

                        brave_path = cfg.get_profile_path(profile_name)
                        if not brave_path:
                            return 0

                        fixed = 0
                        accepted = 0
                        automation = FacebookAutomation(log_callback=self.log, debug=self._debug)
                        try:
                            await automation.start_browser_headless(
                                brave_path, kill_existing=False, viewport=MICRO_VIEWPORT
                            )
                            await automation.go_to_facebook()
                            if not await automation._is_logged_in(timeout=10):
                                return 0

                            # Send to each non-friend
                            for other_name in non_friends:
                                other_url = profile_facebook_urls.get(other_name)
                                if other_url:
                                    self.log(f"    [{idx+1}] '{profile_name}' → sending to '{other_name}'")
                                    status = await automation.send_friend_request_to_profile(other_url)
                                    if status == "sent":
                                        db.record_friend_sent(profile_name, other_name)
                                    elif status in ("accepted", "already_friends"):
                                        db.record_friend_accepted(profile_name, other_name)
                                    elif status == "pending":
                                        db.record_friend_sent(profile_name, other_name)
                                    await asyncio.sleep(1)

                            # Accept via friend requests page
                            fa = await automation.auto_accept_friend_requests(max_accept=50)
                            accepted += fa

                            # Also try inbox as backup
                            if accepted == 0:
                                ib = await automation.accept_friend_requests_from_inbox(max_accept=50)
                                accepted += ib

                            # Also accept from all others via profile visits
                            other_urls = {name: url for name, url in profile_facebook_urls.items()
                                          if name != profile_name}
                            confirmed_list = await automation.accept_friend_requests_by_visiting_profiles(other_urls)
                            for confirmed_name in confirmed_list:
                                if confirmed_name in profile_names and not db.are_friends(profile_name, confirmed_name):
                                    db.record_friend_accepted(profile_name, confirmed_name)

                            # Count how many we fixed this round
                            still_missing = db.get_non_friends(profile_name, profile_names)
                            fixed = len(non_friends) - len(still_missing)
                            self.log(f"    [{idx+1}] '{profile_name}' fixed {fixed} connection(s)")
                        except Exception as e:
                            self.log(f"    [{idx+1}] '{profile_name}' error: {e}")
                        finally:
                            try:
                                await automation.cleanup()
                            except:
                                pass
                        return fixed

                repair_tasks = [_force_repair_one(i, name) for i, name in enumerate(profile_names)]
                await asyncio.gather(*repair_tasks, return_exceptions=True)

                # Re-count
                friends_count = sum(
                    1 for i, a in enumerate(profile_names)
                    for b in profile_names[i + 1:]
                    if db.are_friends(a, b)
                )
                self.log(f"\n  After repair round {repair_round}: {friends_count}/{expected_pairs} pairs connected")

            if friends_count >= expected_pairs:
                self.log(f"\n🎉 ALL {expected_pairs} pairs are now connected!")
            elif repair_round >= MAX_REPAIR_ROUNDS:
                self.log(f"\n⚠️  Reached max repair rounds ({MAX_REPAIR_ROUNDS}). {expected_pairs - friends_count} pair(s) still missing.")

            # ── Groq AI Analysis (with profile_names for matrix) ──
            if profiles_analysis_data and connection_analysis_data:
                analysis_result = self._analyze_friend_connections(
                    profiles_analysis_data, connection_analysis_data,
                    profile_names=profile_names,
                )
        else:
            self.log(f"\nOnly {len(profile_facebook_urls)} profile(s) with URLs — need at least 2")

        # ── CONCURRENT GROUP SYNC ────────────────────────────
        if len(profiles) >= 2:
            self.log(f"\n{'='*50}")
            self.log(f"👥 GROUP SYNC: All profiles join same groups (CONCURRENT)")
            self.log(f"{'='*50}")

            master_groups: list[dict] = []
            group_urls_seen: set[str] = set()

            # Step 1: Collect groups from all profiles concurrently
            self.log(f"\n📋 Step 1: Collecting groups from all profiles...")

            async def _fetch_groups_one(idx: int, pname: str) -> list[dict]:
                async with _sem:
                    brave_path = cfg.get_profile_path(pname)
                    if not brave_path:
                        return []

                    automation = FacebookAutomation(log_callback=self.log, debug=self._debug)
                    try:
                        await automation.start_browser_headless(
                            brave_path, kill_existing=False, viewport=MICRO_VIEWPORT
                        )
                        await automation.go_to_facebook()
                        if not await automation._is_logged_in(timeout=10):
                            return []

                        groups = await automation.fetch_my_groups()
                        if groups:
                            self.log(f"  [{idx+1}/{len(profiles)}] '{pname}' has {len(groups)} group(s)")
                            for g in groups:
                                db.save_profile_groups(pname, [g])
                            return groups
                        else:
                            self.log(f"  [{idx+1}/{len(profiles)}] '{pname}' has no groups")
                            return []
                    except Exception as e:
                        self.log(f"  [{idx+1}/{len(profiles)}] '{pname}' error: {e}")
                        return []
                    finally:
                        try:
                            await automation.cleanup()
                        except:
                            pass

            fetch_tasks = [_fetch_groups_one(i, name) for i, name in enumerate(profiles)]
            fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

            for r in fetch_results:
                if isinstance(r, list):
                    for g in r:
                        url = g.get("url", "").rstrip("/") + "/"
                        if url not in group_urls_seen:
                            group_urls_seen.add(url)
                            master_groups.append({"name": g["name"], "url": url})

            if not master_groups:
                self.log(f"  ⚠️  No groups found — skipping group sync")
            else:
                self.log(f"\n📊 Master list: {len(master_groups)} group(s)")

                # Step 2: Join missing groups concurrently
                self.log(f"\n🔗 Step 2: Joining missing groups (CONCURRENT)...")
                total_joins = 0

                async def _join_groups_one(idx: int, pname: str) -> int:
                    async with _sem:
                        missing_urls = [g["url"] for g in master_groups if not db.has_joined(pname, g["url"])]
                        if not missing_urls:
                            self.log(f"  [{idx+1}/{len(profiles)}] '{pname}' already in all groups ✅")
                            return 0

                        brave_path = cfg.get_profile_path(pname)
                        if not brave_path:
                            return 0

                        joined_count = 0
                        automation = FacebookAutomation(log_callback=self.log, debug=self._debug)
                        try:
                            await automation.start_browser_headless(
                                brave_path, kill_existing=False, viewport=MICRO_VIEWPORT
                            )
                            await automation.go_to_facebook()
                            if not await automation._is_logged_in(timeout=10):
                                return 0

                            for g_url in missing_urls:
                                g_name = next((g["name"] for g in master_groups if g["url"] == g_url), g_url)
                                ok, msg = await automation.join_group(g_url)
                                status = "already_member" if "already" in msg.lower() else ("joined" if ok else "failed")
                                if ok:
                                    joined_count += 1
                                db.record_join(pname, g_url, status, msg)
                                await asyncio.sleep(1)

                            self.log(f"  [{idx+1}/{len(profiles)}] '{pname}' joined {joined_count}/{len(missing_urls)} groups")
                        except Exception as e:
                            self.log(f"  [{idx+1}/{len(profiles)}] '{pname}' error: {e}")
                        finally:
                            try:
                                await automation.cleanup()
                            except:
                                pass
                        return joined_count

                join_tasks = [_join_groups_one(i, name) for i, name in enumerate(profiles)]
                join_results = await asyncio.gather(*join_tasks, return_exceptions=True)
                total_joins = sum(r for r in join_results if isinstance(r, int))
                self.log(f"\n👥 Group sync complete! {total_joins} group joins")

        # ── Final summary ────────────────────────────────────
        self.state = DriverState.STOPPED
        
        pics_set = sum(1 for r in results if r.get("ok") and 
                      r.get("result", {}).get("profile_pic_set"))
        pics_existed = sum(1 for r in results if r.get("ok") and 
                          r.get("result", {}).get("had_profile_pic"))
        
        self.log(f"\n{'='*60}")
        self.log(f"  AUTO-SETUP ALL COMPLETE: {success_count}/{total} profiles successful")
        self.log(f"{'='*60}")
        self.log(f"  Profile Pictures: {pics_set} set, {pics_existed} already existed")

        # Per-profile friend count report
        if len(profile_facebook_urls) >= 2:
            expected_per = len(profile_facebook_urls) - 1
            self.log(f"\n  📊 FRIEND COUNT PER PROFILE (expected: {expected_per} each):")
            all_ok = True
            for name in profile_names:
                fc = db.get_friend_count_for_profile(name)
                status = "✅" if fc >= expected_per else "❌"
                if fc < expected_per:
                    all_ok = False
                missing = db.get_non_friends(name, profile_names)
                missing_str = f" — MISSING: {', '.join(missing)}" if missing else ""
                self.log(f"    {status} {name}: {fc}/{expected_per} friends{missing_str}")

            total_pairs = len(profile_names) * (len(profile_names) - 1) // 2
            connected = sum(
                1 for i, a in enumerate(profile_names)
                for b in profile_names[i + 1:]
                if db.are_friends(a, b)
            )
            self.log(f"\n  Network: {connected}/{total_pairs} pairs connected"
                     + (" ✅ FULLY CONNECTED" if connected >= total_pairs else f" ❌ {total_pairs - connected} pairs missing"))

        self.log(f"{'='*60}")

        self.result_queue.put({
            "type": "auto_setup_all_result",
            "ok": True,
            "total": total,
            "success_count": success_count,
            "pics_set": pics_set,
            "pics_existed": pics_existed,
            "results": results,
        })

    # ── Memory tracking ──────────────────────────────────────

    async def _collect_js_heaps(self):
        """Periodically called from the worker thread to cache JS heap data.

        This runs on the async worker thread where page.evaluate() can
        be safely called. The result is cached in _cached_js_heaps which
        is read by get_memory_stats() from the UI thread.
        """
        heaps: dict[str, float] = {}
        # Snapshot the dict to avoid thread-safety issues with iteration
        for name, auto in list(self._batch_automations.items()):
            if auto and auto.page:
                try:
                    js_heap = await auto.page.evaluate(
                        """() => {
                            try {
                                return performance.memory
                                    ? performance.memory.usedJSHeapSize
                                    : 0;
                            } catch(e) { return 0; }
                        }"""
                    )
                    heaps[name] = js_heap / (1024 * 1024) if js_heap else 0.0
                except Exception:
                    pass
        # Also check single-profile automation
        if self._automation and self._automation.page:
            try:
                js_heap = await self._automation.page.evaluate(
                    """() => {
                        try {
                            return performance.memory
                                ? performance.memory.usedJSHeapSize
                                : 0;
                        } catch(e) { return 0; }
                    }"""
                )
                heaps["active_profile"] = js_heap / (1024 * 1024) if js_heap else 0.0
            except Exception:
                pass
        self._cached_js_heaps = heaps

    def get_memory_stats(self) -> dict:
        """Return current memory stats with caching.

        Thread-safe: reads from _cached_js_heaps (written by worker thread)
        and _batch_automations (snapshotted via list()).

        Returns a dict with:
          - browser_mb: total RSS of all browser processes
          - process_count: number of browser processes
          - system_memory: system-wide RAM info
          - profile_memory: dict of profile_name → estimated MB
          - peak_browser_mb: peak browser memory seen so far
          - has_psutil: whether psutil module is available
        """
        now = time.monotonic()
        if self._memory_cache and (now - self._memory_cache_time) < self._memory_cache_ttl:
            return self._memory_cache

        # Read cached JS heaps (updated by worker thread)
        profile_js_heaps = dict(self._cached_js_heaps)

        # If no heaps from worker thread but automations exist, estimate based on active count
        if not profile_js_heaps:
            active_count = len(list(self._batch_automations.items()))
            if self._automation and self._automation.page:
                active_count += 1
            if active_count > 0 and not profile_js_heaps:
                # No JS data yet — use profile names from batch automations
                for name in list(self._batch_automations.keys()):
                    profile_js_heaps[name] = 19.0  # default estimate from benchmark

        from src.core.memory_tracker import HAS_PSUTIL

        snap = self._memory_tracker.snapshot(profile_js_heaps)

        stats = {
            "browser_mb": round(snap.browser_mb, 1),
            "process_count": snap.process_count,
            "system_memory": snap.system,
            "profile_memory": snap.profile_memory,
            "profile_js_heaps": snap.profile_js_heaps,
            "peak_browser_mb": round(self._memory_tracker.peak_mb, 1),
            "has_psutil": HAS_PSUTIL,
            "batch_running": self._batch_running,
        }

        self._memory_cache = stats
        self._memory_cache_time = now
        return stats

    # ── Batch size configuration ───────────────────────────────

    @property
    def batch_size(self) -> int:
        """Get the current batch size (concurrent profiles)."""
        return self._batch_size

    @batch_size.setter
    def batch_size(self, value: int):
        """Set batch size, clamped to [1, 20]."""
        self._batch_size = max(1, min(20, value))
        # Persist to config so it survives restarts
        cfg.save_setting("batch_size", self._batch_size)

    # ── Concurrent batch processing ──────────────────────────

    # Only a session Facebook simply expired is worth retrying on our own.
    # 2FA, a wrong password, a bad username and a disabled account are all
    # decisions a re-login cannot change, and hammering them is how an account
    # gets locked rather than recovered.
    # How long a profile's shares pause after a refusal. Facebook lifts these
    # by itself, so both are pauses, not verdicts. A refusal that NAMES the
    # account earns the long one; a share that simply never went through earns
    # the short one - enough to stop a run hammering it, not enough to write
    # the profile off over one bad minute.
    SHARE_RESTRICTION_HOURS = 12
    SHARE_FAILURE_PAUSE_HOURS = 2

    RELOGIN_REASONS = ("logged out or session expired", "session expired",
                       "no home page")
    # Per profile, so a profile Facebook keeps expiring cannot become a loop.
    RELOGIN_COOLDOWN_SECONDS = 1800

    # A login run walks the roster in batches with a rest between them. Five
    # at a time is what the operator asked for; the pause is the anti-spam
    # lever, since the logins themselves cannot overlap (Brave's singleton).
    # How long a fresh login gets to actually become a live session.
    # Facebook still has redirects to finish and c_user/xs to set after the
    # credentials go in; checking once, immediately, wrote off accounts that
    # only needed another second or two.
    SESSION_CONFIRM_S = 25
    # How many logins run together when the browser allows it (Chromium,
    # one directory per account). Brave ignores this and stays sequential.
    # 25 tiled the screen 5x5, and 25 logins from one IP inside a minute is
    # the pattern Facebook prices highest: the first run that way produced one
    # login in 73 attempts. Ten at a time still fills the screen and spreads
    # the run out. The grid follows this number - ten tiles 4x3.
    LOGIN_PARALLEL = 10
    # Sequential (Brave) spacing only; a parallel run pauses once per wave.
    LOGIN_BATCH_SIZE = 5
    LOGIN_BATCH_PAUSE_MIN = 2.0

    def _relogin_allowed(self, profile_name: str) -> bool:
        if not cfg.get_setting("auto_relogin", True):
            return False
        account = db.account_for_profile(profile_name) or {}
        if account.get("status") == "disabled":
            return False
        reason = (account.get("status_reason") or "").strip().lower()
        if reason and reason not in self.RELOGIN_REASONS:
            return False
        last = getattr(self, "_relogin_last", {}).get(profile_name, 0.0)
        return (time.monotonic() - last) >= self.RELOGIN_COOLDOWN_SECONDS

    async def _relogin_profile(self, profile_name: str,
                               why: str = "Session expired",
                               slot: int | None = None, wave: int = 1) -> bool:
        """Log a profile in inside its real Brave profile.

        `why` is the reason shown in the log: the default for the sweep and
        the batch demotion, "Login requested" when the operator asked.

        Sequential and inside the profile's REAL Brave user-data-dir. It has to
        be: Brave binds cookie encryption to the user-data-dir, so a login
        performed in a copy and written back leaves a profile whose c_user/xs
        cannot be decrypted - dead, while still looking logged in. That is why
        scripts/login_parallel.py must not be used for this.
        """
        from src.core.facebook_automation import FacebookAutomation, LOGIN_FLAGS
        from src.storage import state_cache

        creds = db.credentials_for_profile(profile_name)
        if not creds:
            self.log(f"  ↻ '{profile_name}': no password on the roster row - "
                     f"cannot re-login automatically")
            return False
        username, password = creds
        brave_path = cfg.get_profile_path(profile_name)
        if not brave_path:
            self.log(f"  ↻ '{profile_name}': no Brave profile path")
            return False

        if not hasattr(self, "_relogin_last"):
            self._relogin_last = {}
        self._relogin_last[profile_name] = time.monotonic()

        self.log(f"  ↻ {why} - logging '{profile_name}' in...")
        auto = FacebookAutomation(log_callback=lambda m: None)
        try:
            # Visible and tiled when the operator asked to watch the wave;
            # headless otherwise, which is what an unattended run wants.
            show = browser_choice.show_login_windows()
            tile = (slot, wave) if (show and slot is not None) else None
            await auto.start_browser(brave_path, headless=not show,
                                     flags=LOGIN_FLAGS, tile=tile)
            await auto.go_to_facebook()
            ok, msg = True, "already logged in"
            if not await self._session_is_live(auto):
                # Headless: no one can answer a 2FA prompt, so take the
                # verdict at once instead of burning 120 s per account.
                # Waiting 120 s for a 2FA code only pays off when someone
                # will type one. In a bulk run nobody can - the codes are on
                # phones this PC does not have - so the wait is opt-in with
                # the login_wait_2fa setting and off by default. A captcha is
                # different: handle_recaptcha still gives a visible window its
                # full wait, because a person can answer that one.
                wait_2fa = show and bool(cfg.get_setting("login_wait_2fa", False))
                ok, msg = await auto.login_with_credentials(
                    username, password, wait_for_2fa=wait_2fa)
                if ok and not await self._wait_session_live(auto):
                    ok, msg = False, ("signed in but never reached the home "
                                      "page - Facebook is gating this account")
            # A captcha is the one failure a person can clear in seconds, so
            # it is worth a window even in a background run: everything else
            # stays headless and this account alone comes to the front.
            if not ok and login_reason(msg) == "captcha" and slot is not None:
                ok, msg = await self._retry_visible(auto, profile_name, brave_path,
                                                    username, password, slot, wave)
            if ok:
                await self._record_and_publish(profile_name, True, "logged_in")
                state_cache.invalidate(profile_name)   # force a fresh extract
                self.log(f"  ✓ '{profile_name}' logged back in ({msg})")
                return True
            # Facebook's own message first; the URL classification is only
            # the fallback for a failure it did not explain.
            status = login_reason(msg) or await auto._classify_account_access()
            if status == auto.LOGGED_IN:
                # The message said one thing, the browser says the session is
                # live. The browser wins - it is looking at the account.
                await self._record_and_publish(profile_name, True, "logged_in")
                state_cache.invalidate(profile_name)
                self.log(f"  ✓ '{profile_name}' is logged in after all ({msg})")
                return True
            await self._record_and_publish(profile_name, False, status)
            self.log(f"  ✗ '{profile_name}' could not be logged back in: {msg}")
            return False
        except Exception as e:
            self.log(f"  ✗ '{profile_name}' re-login error: {str(e)[:120]}")
            return False
        finally:
            try:
                await auto.quit()
            except Exception:
                pass

    async def _retry_visible(self, auto, profile_name: str, brave_path: str,
                             username: str, password: str,
                             slot: int, wave: int) -> tuple[bool, str]:
        """Reopen this one account in a visible tile so the operator can answer
        its captcha, and log in again there.

        The headless attempt cannot be handed over: nothing is on screen to
        click. Only the accounts that hit a captcha pay for the second
        launch; the rest of the wave never leaves the background.
        """
        from src.core.facebook_automation import LOGIN_FLAGS

        self.log(f"  ↻ '{profile_name}' hit a captcha - opening a window for it")
        try:
            await auto.quit()
        except Exception:
            pass
        await auto.start_browser(brave_path, headless=False,
                                 flags=LOGIN_FLAGS, tile=(slot, wave))
        await auto.go_to_facebook()
        if await self._session_is_live(auto):
            return True, "already logged in"
        ok, msg = await auto.login_with_credentials(username, password,
                                                    wait_for_2fa=True)
        if ok and not await self._wait_session_live(auto):
            return False, ("signed in but never reached the home page - "
                           "Facebook is gating this account")
        return ok, msg

    async def _wait_session_live(self, auto, seconds: float | None = None,
                                 poll: float = 2.0) -> bool:
        """True as soon as the session is live, or False when the window
        closes. Polling rather than one instant look: a slow redirect is the
        normal case, not a failed login."""
        deadline = time.monotonic() + (self.SESSION_CONFIRM_S if seconds is None else seconds)
        while True:
            try:
                if await self._session_is_live(auto):
                    return True
            except Exception:
                pass
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0 if getattr(self, "_fast_tests", False) else poll)

    @staticmethod
    async def _session_is_live(auto) -> bool:
        """Both session cookies present AND the browser is on the home page.

        Facebook issues c_user and xs before a checkpoint, so cookies alone
        call a gated account logged in.
        """
        try:
            cookies = await auto.context.cookies()
        except Exception:
            return False
        names = {c.get("name") for c in cookies
                 if "facebook" in (c.get("domain") or "")}
        if not {"c_user", "xs"} <= names:
            return False
        try:
            return auto._is_home_url(auto.page.url)
        except Exception:
            return False

    async def _login_failure(self, auto, profile_name: str) -> dict:
        """Why did the login check fail: a dead session, or a slow page?

        _is_logged_in() polls for 15s. Under load - eight contexts plus a live
        watch on the same machine - a page that has simply not finished
        loading returns False, and that used to be reported as "Not logged in",
        which demoted the account AND deleted its cached session. Six accounts
        that had been commenting and sharing minutes earlier were wiped that
        way in one run.

        record_login_check() already refuses to act on an inconclusive check;
        this asks the same classifier so that guard can do its job.
        """
        try:
            status = await auto._classify_account_access()
        except Exception:
            status = "unknown"
        from src.core.facebook_automation import FacebookAutomation
        if status == FacebookAutomation.LOGGED_IN:
            return {"profile_name": profile_name, "ok": True, "needs_login": False,
                    "message": "logged in"}
        if status in ("unreachable", "unknown"):
            # Deliberately worded to match none of the needs_login keywords:
            # an inconclusive check must never demote a working account.
            return {"profile_name": profile_name, "ok": False,
                    "needs_login": False,
                    "message": f"could not confirm sign-in ({status}) - "
                               f"page did not load, profile left active"}
        return {"profile_name": profile_name, "ok": False,
                "needs_login": True,
                "message": f"Not logged in ({status.replace('_', ' ')})"}

    @staticmethod
    def _session_recorded_live(profile_name: str) -> bool:
        """Whether the roster says this account is logged in.

        The database's own verdict first - it is written by a login run or a
        login check that saw the home page. The sheet's LOGGED IN cell counts
        too, and nothing else does: "NOT LOGGED IN / SESSION EXPIRED"
        contains the same words, so the match is exact.
        """
        account = db.account_for_profile(profile_name) or {}
        if (account.get("status") or "") == "ok":
            return True
        return (account.get("sheet_status") or "").strip().upper() == "LOGGED IN"

    async def _do_batch(self, items: list[dict]):
        """Process queue items with all profile pages opened up front.

        How it works:
          1. Load storage states from the disk cache; extract only cache
             misses (sequential — Chromium's process singleton forbids two
             persistent contexts on the shared User Data dir — but on the
             fast no-navigation path, ~4-6s each instead of ~10-20s)
          2. Launch ONE shared Chromium browser
          3. Open contexts/pages for ALL active profiles concurrently
             (they share the one browser, so no singleton constraint);
             very large fleets fall back to chunks to cap RAM
          4. Process items ONE AT A TIME with the configured anti-spam
             delay between actions (deliberate — protects the accounts)
          5. Teardown contexts, report, cleanup
        """
        self._batch_running = True

        from src.storage import state_cache

        # Watch is not an action performed once and closed - it is where the
        # profiles stay when the run is over, so it is pulled out before the
        # count and started after the batch instead of processed as an item.
        watch_items = [i for i in items if i.get("action_type") == "watch"]
        items = [i for i in items if i.get("action_type") != "watch"]
        total = len(items)

        if watch_items and not items:
            # Nothing to perform first: open the live now. Going through the
            # batch machinery would launch a shared browser, walk the
            # profiles in fives and tear it all down again before the first
            # page ever reached the stream.
            url = watch_items[0].get("post_url") or ""
            minutes = watch_items[0].get("watch_minutes")
            watchers = [i["profile_name"] for i in watch_items]
            self.log(f"▶ Watching live directly: {len(watchers)} profile(s)"
                     + (f" for {minutes:g} min" if minutes
                        else " for the whole live, start to end"))
            self._batch_running = False
            self.result_queue.put({"type": "batch_result", "ok": True,
                                   "results": [], "total": 0})
            await self._do_watch(url, minutes=minutes, profile_names=watchers)
            return

        self.log(f"Starting batch: {total} item(s)"
                 + (f", then {len(watch_items)} profile(s) stay to watch"
                    if watch_items else ""))

        # Get unique profiles
        unique_profiles = list({item["profile_name"] for item in items})

        # Every profile takes part, whatever the roster records. A stored
        # status is a verdict from an earlier run, not the state of the
        # session now, and the operator asked to see the whole fleet act and
        # judge from the per-item results. A dead session still costs a
        # launch and a page load and still shows up as a failed item - that
        # is the price of not filtering, and it is the operator's call.
        stale = [p for p in unique_profiles if not self._session_recorded_live(p)]
        if stale:
            self.log(f"  {len(stale)} profile(s) were not logged in at their last "
                     f"check - attempting them anyway")

        # ── Phase 1: Load cached states, extract only the misses ──
        states: dict[str, dict | None] = {}
        to_extract: list[str] = []
        for profile_name in unique_profiles:
            cached = state_cache.load_state(profile_name)
            if cached is not None:
                states[profile_name] = cached
            else:
                to_extract.append(profile_name)
        if len(states):
            self.log(f"  ⚡ {len(states)} profile(s) loaded from login-state cache")

        if to_extract:
            self.log(f"Extracting login state for {len(to_extract)} profile(s)...")
        for p_idx, profile_name in enumerate(to_extract):
            brave_path = cfg.get_profile_path(profile_name)
            if not brave_path:
                self.log(f"  ❌ Profile '{profile_name}' not found — skipping")
                states[profile_name] = None
                continue
            self.log(f"  Extracting '{profile_name}'...")
            temp_auto = self._create_temp_automation()
            try:
                # Fast path: no facebook.com navigation — zero FB traffic,
                # so no anti-throttle pause is needed between profiles.
                # Login validity is verified live before every action.
                state = await temp_auto.extract_storage_state(
                    brave_path, skip_navigation=True)
                if state is None:
                    self.log(f"  ⚠️  Could not extract state for '{profile_name}'")
                else:
                    state_cache.save_state(profile_name, state)
                states[profile_name] = state
            except Exception as e:
                self.log(f"  ❌ Failed to extract '{profile_name}': {e}")
                states[profile_name] = None
            # Brief pause so the previous browser fully releases the
            # User Data singleton lock before the next launch.
            if p_idx < len(to_extract) - 1:
                await asyncio.sleep(0.5)

        # ── Phase 2: Launch single shared browser ──────────
        from src.core.facebook_automation import FacebookAutomation

        self._batch_pw = await async_playwright().start()
        self._batch_automations.clear()

        # Facebook switches to a compact/touch-oriented reaction control at the
        # 640px viewport.  That control keeps the reaction tray open only during
        # a long press, so the normal desktop hover/click flow cannot select
        # Love/Care/etc.  Give batches containing a non-Like reaction a desktop
        # viewport; keep the smaller viewport for all other (cheaper) work.
        needs_desktop_post_ui = any(
            item.get("action_type") == "comment" or (
                item.get("action_type") == "react"
                and (item.get("reaction") or "like").strip().lower() != "like"
            )
            for item in items
        )
        batch_viewport = SMALL_VIEWPORT if needs_desktop_post_ui else TINY_VIEWPORT

        # Browser render mode. Facebook serves a STRIPPED page to the old
        # headless engine — the post body renders but the interactive footer
        # (Like/Comment/Share bar + comment composer) never does, which is why
        # comments fail with "textbox not found". The new headless engine
        # renders like real Chrome while staying hidden; "visible" shows real
        # windows as a guaranteed fallback.
        #   headless_new (default) → hidden, real rendering  [fixes comments]
        #   visible               → real on-screen windows   [fallback]
        #   headless              → legacy headless          [lowest RAM, breaks comments]
        browser_mode, launch_headless, launch_args = \
            self._browser_launch_mode(batch_viewport)
        self.log(f"Launching shared browser [{browser_mode}]...")
        shared_browser = await self._launch_browser(
            self._batch_pw, launch_headless, launch_args)

        # ── Phase 3: Open ALL profile pages at once ────────
        # Contexts on the shared browser are plain incognito contexts —
        # no user-data dir, no singleton lock — so they can open
        # concurrently. Pages idle cheaply (resource blocking on, no FB
        # DOM loaded) until their items run. Only very large fleets fall
        # back to chunked batches to cap RAM.
        MAX_ALL_AT_ONCE = 24
        active_profiles = [p for p in unique_profiles if states.get(p) is not None]
        if len(active_profiles) <= MAX_ALL_AT_ONCE:
            batches = [active_profiles] if active_profiles else []
        else:
            batches = [active_profiles[i:i + self.batch_size]
                       for i in range(0, len(active_profiles), self.batch_size)]

        self.result_queue.put({
            "type": "batch_progress", "current": 0, "total": total,
            "message": f"Opening {len(active_profiles)} profile(s), "
                       f"{total} item(s) queued...",
        })

        processed = 0
        # Attempts and successes are counted apart: "53/53 done" was read as
        # 53 accounts having acted, when it only ever meant 53 items tried.
        success_count = 0
        handled: set[str] = set()  # profiles that actually produced a result

        for batch_idx, batch_profiles in enumerate(batches):
            self.log(f"── Batch {batch_idx + 1}/{len(batches)}: "
                     f"{', '.join(batch_profiles)} ──")

            # Open every profile's context/page concurrently (they share
            # the one browser process, so this is cheap and lock-free).
            self._batch_automations.clear()
            init_sem = asyncio.Semaphore(5)  # smooth the launch burst

            async def _open_one(profile_name: str):
                async with init_sem:
                    auto = FacebookAutomation(log_callback=self.log,
                                              debug=self._debug)
                    await auto.init_from_storage(
                        shared_browser, states.get(profile_name),
                        viewport=batch_viewport)
                    self._batch_automations[profile_name] = auto

            open_results = await asyncio.gather(
                *(_open_one(p) for p in batch_profiles),
                return_exceptions=True)
            for p, res in zip(batch_profiles, open_results):
                if isinstance(res, Exception):
                    self.log(f"  ⚠️  Could not open page for '{p}': {res}")
            self.log(f"  ⚡ {len(self._batch_automations)} profile page(s) open")

            # Gather items belonging to this batch (only profiles whose
            # page actually opened are in _batch_automations)
            batch_items = [(i, item) for i, item in enumerate(items)
                           if item["profile_name"] in self._batch_automations]
            handled.update(item["profile_name"] for _, item in batch_items)

            # Process batch items concurrently (within the batch only)
            async def _process_one(index: int, item: dict) -> dict:
                profile_name = item["profile_name"]
                auto = self._batch_automations.get(profile_name)
                if not auto:
                    return {"profile_name": profile_name, "ok": False,
                            "message": "Profile context not available"}

                action_type = item.get("action_type", "group")
                is_text_post = action_type == "post_text"
                is_timeline = action_type == "timeline"
                is_react = action_type == "react"
                is_comment = action_type == "comment"
                is_share = action_type == "share"
                is_story = action_type == "story"

                if is_text_post:
                    target = "Text Post"
                elif is_timeline:
                    target = "Timeline"
                elif is_react:
                    target = f"React ({item.get('reaction', 'like')})"
                elif is_comment:
                    target = "Comment"
                elif is_share:
                    target = "Timeline Share"
                elif is_story:
                    target = "Story"
                else:
                    target = item.get("group_name", "?")

                self.log(f"  [{index + 1}/{total}] {profile_name} → {target}")

                # Two reasons never to attempt a share. Neither applies to a
                # comment or a reaction, which stay allowed either way.
                if is_timeline or is_share or is_story:
                    post_url = item.get("post_url", "")
                    if post_url and db.has_shared(profile_name, post_url, target):
                        msg = "already shared this link - skipped"
                        self.log(f"  [{index + 1}/{total}] ⏭️  {profile_name}: {msg}")
                        return {"profile_name": profile_name, "ok": True,
                                "message": msg, "skipped": True}
                    held = db.share_restriction(profile_name)
                    if held:
                        reason, seen_at = held
                        msg = (f"shares paused for this account after a "
                               f"refusal at {seen_at} ({reason[:70]})")
                        self.log(f"  [{index + 1}/{total}] ⏭️  {profile_name}: {msg}")
                        return {"profile_name": profile_name, "ok": False,
                                "message": msg, "skipped": True}

                try:
                    if is_react:
                        # For reactions: Go DIRECTLY to the post URL
                        # Don't load Facebook home page first (prevents caching/redirects)
                        reaction = item.get("reaction") or "like"
                        post_url = item["post_url"]
                        self.log(f"  📍 Reacting to URL: {post_url}")
                        ok, msg = await auto._auto_react(post_url, reaction)
                    elif is_comment:
                        # For comments: Also go directly to post URL
                        post_url = item["post_url"]
                        self.log(f"  📍 Commenting on URL: {post_url}")
                        result = await auto._auto_comment(post_url, item.get("comment_text", ""))
                        ok = result if isinstance(result, bool) else True
                        msg = "Commented" if ok else (getattr(
                            auto, "last_comment_error", "") or "Failed to comment")
                    elif is_text_post:
                        # For text posts: Need to go to Facebook first
                        await auto.go_to_facebook()
                        logged_in = await auto._is_logged_in(timeout=15)
                        if not logged_in:
                            return await self._login_failure(auto, profile_name)
                        
                        # Debug: Log what we're about to post
                        img_count = len(item.get("image_paths") or [])
                        self._log(f"📝 Posting text with {img_count} image(s)")
                        if img_count > 0:
                            self._log(f"   Image paths: {item.get('image_paths')}")
                        
                        ok, msg = await auto.post_text_to_timeline(
                            item.get("text", ""),
                            image_paths=item.get("image_paths"))
                        
                        # AGGRESSIVE CLEANUP: Ensure dialog is fully closed and page is reset
                        try:
                            await asyncio.sleep(1)
                            # Press Escape multiple times to close any dialogs
                            for _ in range(3):
                                await auto.page.keyboard.press("Escape")
                                await asyncio.sleep(0.3)
                            # Navigate to home to reset page state
                            await auto.page.goto("https://www.facebook.com/", 
                                                timeout=15000, 
                                                wait_until="domcontentloaded")
                            await asyncio.sleep(1)
                            self.log(f"  ✅ Cleaned up page for {profile_name}")
                        except Exception as e:
                            self.log(f"  ⚠️  Cleanup warning: {e}")
                    elif is_timeline:
                        # For timeline shares: Need to go to Facebook first
                        await auto.go_to_facebook()
                        logged_in = await auto._is_logged_in(timeout=15)
                        if not logged_in:
                            return await self._login_failure(auto, profile_name)
                        
                        ok, msg = await auto.share_post_to_timeline(
                            item["post_url"],
                            comment_text=item.get("comment_text") or None,
                            reaction=item.get("reaction") or None)
                    elif is_share:
                        # Share to timeline feed only
                        await auto.go_to_facebook()
                        logged_in = await auto._is_logged_in(timeout=15)
                        if not logged_in:
                            return await self._login_failure(auto, profile_name)

                        ok, msg = await auto.share_post_to_feed(item["post_url"])
                    elif is_story:
                        # Share to story only
                        await auto.go_to_facebook()
                        logged_in = await auto._is_logged_in(timeout=15)
                        if not logged_in:
                            return await self._login_failure(auto, profile_name)

                        ok, msg = await auto.share_post_to_story(item["post_url"])
                    else:
                        # For group shares: Need to go to Facebook first
                        await auto.go_to_facebook()
                        logged_in = await auto._is_logged_in(timeout=15)
                        if not logged_in:
                            return await self._login_failure(auto, profile_name)
                        
                        ok, msg = await auto.share_post_to_group(
                            item["post_url"], target,
                            comment_text=item.get("comment_text") or None,
                            reaction=item.get("reaction") or None)

                    # Persist result to database so it isn't repeated on next run
                    try:
                        if is_text_post:
                            db.log_activity("post_text", profile_name, msg)
                        elif is_react:
                            db.log_activity("react", profile_name, msg)
                        elif is_comment:
                            db.log_activity("comment", profile_name, msg)
                        else:
                            db.record_share(
                                profile_name,
                                item.get("post_url", ""),
                                target,
                                "shared" if ok else "failed",
                                msg,
                            )
                            # Remember a share refusal that is about the
                            # ACCOUNT, so later runs skip it instead of
                            # re-attempting; a share that works proves the
                            # restriction is over.
                            if ok:
                                db.clear_share_restriction(profile_name)
                            elif "restricting this account" in (msg or ""):
                                db.record_share_restriction(
                                    profile_name, msg,
                                    self.SHARE_RESTRICTION_HOURS)
                            else:
                                # Every retry route was already spent getting
                                # here, so trying again immediately is forcing
                                # it. Pause briefly instead.
                                db.record_share_restriction(
                                    profile_name, msg or "share did not go through",
                                    self.SHARE_FAILURE_PAUSE_HOURS)
                    except Exception as db_err:
                        self.log(f"  ⚠️  Failed to save result for '{profile_name}': {db_err}")

                    self.log(f"  [{index + 1}/{total}] "
                             f"{'✅' if ok else '❌'} {profile_name}: {msg}")
                    return {"profile_name": profile_name, "ok": ok, "message": msg}

                except Exception as e:
                    self.log(f"  [{index + 1}/{total}] {profile_name}: error — {e}")
                    try:
                        if is_text_post:
                            db.log_activity("post_text", profile_name, f"error: {e}")
                        elif is_react:
                            db.log_activity("react", profile_name, f"error: {e}")
                        elif is_comment:
                            db.log_activity("comment", profile_name, f"error: {e}")
                        else:
                            db.record_share(
                                profile_name,
                                item.get("post_url", ""),
                                target,
                                "error",
                                str(e),
                            )
                    except Exception:
                        pass
                    return {"profile_name": profile_name, "ok": False, "message": str(e)}

            # Items run ONE AT A TIME with a randomized delay between them
            # — deliberate anti-spam pacing (tune via CONFIGURE_DELAYS.bat).
            relogin_queue = getattr(self, "_relogin_queue", None)
            if relogin_queue is None:
                relogin_queue = self._relogin_queue = set()
            self.log(f"\n🔄 Processing {len(batch_items)} item(s) with anti-spam delays...")

            batch_results = []
            comment_delays = cfg.get_comment_delays()

            for i, (idx, item) in enumerate(batch_items):
                # Delay between actions (except before the first one)
                if i > 0:
                    delay = random.uniform(
                        comment_delays["between_comments_min"],
                        comment_delays["between_comments_max"]
                    )
                    action = item.get("action_type", "action")
                    self.log(f"   ⏳ Waiting {delay:.1f}s before next {action}...")
                    await asyncio.sleep(delay)

                result = await _process_one(idx, item)
                batch_results.append(result)
            
            # Clean up contexts after all are done
            for idx, item in batch_items:
                profile_name = item.get("profile_name", "Unknown")
                auto = self._batch_automations.get(profile_name)
                if auto:
                    try:
                        self.log(f"   🔒 Closing context for {profile_name}...")
                        await auto.cleanup()
                    except Exception as e:
                        self.log(f"   ⚠️  Cleanup warning for {profile_name}: {e}")

            # Report batch results
            for i, result in enumerate(batch_results):
                idx, item = batch_items[i]
                processed += 1
                # No Exception branch here: batch_results is filled by a
                # direct `await _process_one(...)`, not gather(
                # return_exceptions=True), so a raise propagates out of the
                # loop instead of arriving as a result.
                if isinstance(result, dict):
                    if result.get("ok"):
                        success_count += 1
                    msg = result.get("message", "")
                    low = msg.lower()
                    is_rate_limited = ("rate limit" in low
                                       or "too frequently" in low)
                    # Detect a dead/expired session across ALL action phrasings
                    # (comment path says "logged out or session expired",
                    # share/timeline say "not logged in", non-Like react says
                    # "login overlay"). A structured flag from the automation
                    # wins over the message text when present.
                    needs_login = bool(result.get("needs_login")) or any(
                        k in low for k in (
                            "not logged in", "login overlay", "logged out",
                            "session expired", "not logged-in"))
                    if needs_login:
                        # Self-healing: drop the cached state so the next
                        # run re-extracts this profile fresh, and clear the
                        # 'ok' status so the count, the filter and the sheet
                        # stop calling this profile active.
                        pname = result.get("profile_name", "")
                        state_cache.invalidate(pname)
                        await self._record_and_publish(pname, False,
                                                       "session expired")
                        # Queued, not run here: this browser is mid-batch and a
                        # re-login opens the profile's real user-data-dir.
                        if self._relogin_allowed(pname):
                            relogin_queue.add(pname)
                    self.result_queue.put({
                        "type": "batch_item_result",
                        "ok": result.get("ok", False),
                        "profile_name": result.get("profile_name", "?"),
                        "message": msg, "rate_limited": is_rate_limited,
                        "needs_login": needs_login,
                    })

                self.result_queue.put({
                    "type": "batch_progress",
                    "current": processed, "total": total,
                    "succeeded": success_count,
                    "message": f"{processed}/{total} attempted, {success_count} ok",
                })

            # Close this batch's contexts → frees RAM immediately
            for auto in self._batch_automations.values():
                try:
                    await auto.close_context()
                except Exception:
                    pass
            self._batch_automations.clear()
            import gc
            gc.collect()
            self.log(f"  Batch {batch_idx + 1} complete — contexts closed, memory freed")

        # ── Report items whose profile never got processed ──
        # A profile is skipped when extraction returned None (bad path /
        # unreadable session) or its page failed to open. Without this,
        # those queue rows would receive no terminal status and the
        # progress count would never reach total.
        for item in items:
            pname = item.get("profile_name", "?")
            if pname in handled:
                continue
            processed += 1
            reason = ("login-state extraction failed — open the profile in "
                      "the app and re-login" if states.get(pname) is None
                      else "profile page could not be opened")
            state_cache.invalidate(pname)  # force fresh extraction next run
            self.result_queue.put({
                "type": "batch_item_result", "ok": False,
                "profile_name": pname,
                "message": f"Skipped: {reason}",
                "needs_login": True,
            })
            self.result_queue.put({
                "type": "batch_progress", "current": processed,
                "total": total, "succeeded": success_count,
                "message": f"{processed}/{total} attempted, {success_count} ok",
            })

        # ── Phase 4: Final cleanup ─────────────────────────
        self.log("Cleaning up browser...")
        await self._cleanup_batch()

        self._batch_running = False
        self.state = DriverState.STOPPED
        self.result_queue.put({
            "type": "batch_result", "ok": True, "total": total,
        })
        # Now that the shared browser is closed, nothing holds Brave's
        # singleton lock, so expired sessions can be restored in place.
        pending = getattr(self, "_relogin_queue", None) or set()
        if pending:
            names = sorted(pending)
            pending.clear()
            self.log(f"↻ Auto re-login: {len(names)} profile(s) whose session "
                     f"Facebook expired")
            restored = 0
            for name in names:
                if await self._relogin_profile(name):
                    restored += 1
            self.log(f"↻ Auto re-login: {restored}/{len(names)} restored")
        self.log(f"Batch complete: {success_count}/{total} successful")

        if watch_items:
            # The post is already open in every context, but those close with
            # the batch; _do_watch reopens them with media interception off,
            # which is what keeps a live video actually playing.
            url = watch_items[0].get("post_url") or ""
            minutes = watch_items[0].get("watch_minutes")
            watchers = [i["profile_name"] for i in watch_items]
            self.log(f"▶ Staying on the post to watch: {len(watchers)} profile(s)"
                     + (f" for {minutes:g} min" if minutes
                        else " for the whole live, start to end"))
            await self._do_watch(url, minutes=minutes, profile_names=watchers)

    async def _cleanup_batch(self):
        """Close all profile automations and the shared browser.

        The watch is deliberately untouched. Its pages ARE the viewers: they
        have to stay open with the video playing after the run is over, so
        _watch_pw, _watch_browser and _watch_autos belong to _stop_watch
        alone - reached by the Stop button, by a new watch replacing this one,
        or by quitting the app.
        """
        for name, auto in list(self._batch_automations.items()):
            try:
                await auto.close_context()
            except Exception:
                pass
        self._batch_automations.clear()

        if self._batch_pw:
            try:
                await self._batch_pw.stop()
            except Exception:
                pass
            self._batch_pw = None
        gc.collect()

    def _create_temp_automation(self):
        """Create a FacebookAutomation instance for temporary use (no log callback needed)."""
        from src.core.facebook_automation import FacebookAutomation
        return FacebookAutomation(log_callback=self.log, debug=self._debug)

    async def _do_cleanup(self):
        await self._cleanup_batch()
        if self._automation:
            try:
                self.log("Closing browser...")
                await self._automation.cleanup()
            except Exception:
                pass
        self.state = DriverState.STOPPED
        self.result_queue.put({"type": "cleanup_result", "ok": True})

    async def _do_logout(self):
        """Log out: close browser, clear saved credentials, reset state."""
        await self._cleanup_batch()
        if self._automation:
            try:
                self.log("Closing browser for logout...")
                await self._automation.quit()
            except Exception:
                pass
        from src.storage import config_manager as cfg
        cfg.clear_credentials()
        self.state = DriverState.STOPPED
        self.result_queue.put({"type": "logout_result", "ok": True})
        self.log("Logged out and credentials cleared.")

    async def _do_quit(self):
        await self._cleanup_batch()
        await self._stop_watch()
        if self._automation:
            try:
                await self._automation.quit()
            except Exception:
                pass
        self.state = DriverState.STOPPED

    @staticmethod
    def _browser_launch_mode(viewport: dict,
                             autoplay: bool = False,
                             flags: list | None = None) -> tuple[str, bool, list[str]]:
        """(mode name, headless flag, launch args) for the configured render mode.

        The single owner of the "Browser mode" setting, so every browser the
        app opens obeys the dropdown - the queue runner and the live watch
        alike. Facebook serves a STRIPPED page to the old headless engine, so:
          headless_new (default) -> hidden, renders like real Chrome
          visible                -> real on-screen windows
          headless               -> legacy headless [lowest RAM, breaks comments]

        flags defaults to MEMORY_FLAGS. The watch passes WATCH_FLAGS, which
        drops the two caps that starve concurrent video decode.
        """
        from src.core.facebook_automation import MEMORY_FLAGS
        mode = cfg.get_setting("browser_mode", "headless_new")
        args = [f"--window-size={viewport['width']},{viewport['height']}",
                *(MEMORY_FLAGS if flags is None else flags)]
        if autoplay:
            # Chromium blocks autoplay without a user gesture, so a Facebook
            # video page loads but stays PAUSED - the page is open and no view
            # is ever counted. Watch exists to play the video, so it asks for
            # autoplay; a queue run does not and must not stream video.
            args.append("--autoplay-policy=no-user-gesture-required")
        if mode == "headless_new":
            # Playwright must not add its own --headless: our flag selects the
            # new engine, which is what actually hides the window.
            args.append("--headless=new")
            return mode, False, args
        if mode == "visible":
            return mode, False, args
        return mode, True, args

    async def _launch_browser(self, pw, headless: bool, args: list,
                              attempts: int = 3):
        """Launch the shared browser, retrying a browser that dies at startup.

        Brave updates itself in the background. A launch that lands in that
        window starts the new binary and it exits immediately, which Playwright
        reports as "Target page, context or browser has been closed" with
        exitCode=0 in the log. Nothing is wrong with the flags and the next
        attempt a few seconds later succeeds, so a transient failure must not
        cost the whole batch.
        """
        from src.core.facebook_automation import CHROME_PATH
        last = None
        for attempt in range(1, attempts + 1):
            try:
                return await pw.chromium.launch(executable_path=browser_choice.executable_path(),
                                                headless=headless, args=args)
            except Exception as e:
                last = e
                if attempt == attempts:
                    break
                wait = 3 * attempt
                self.log(f"  ⚠️  Browser launch failed (attempt {attempt}/"
                         f"{attempts}): {str(e).splitlines()[0][:120]}")
                self.log(f"  Retrying in {wait}s - Brave may be mid-update...")
                await asyncio.sleep(wait)
        raise last

    # Re-checked this often while a watch is running. Long enough to cost
    # nothing, short enough that a stall is measured in seconds. Randomised
    # rather than fixed: a poll landing on the same 15.0s tick for two hours
    # is a machine signature, and nothing here needs a precise cadence.
    WATCH_POLL_MIN_SECONDS = 10
    WATCH_POLL_MAX_SECONDS = 20

    # How often the heartbeat line is printed. Also randomised, so "every
    # ~2 min" is an average rather than a metronome.
    WATCH_BEAT_MIN_SECONDS = 90
    WATCH_BEAT_MAX_SECONDS = 180

    # A page is stalled when currentTime advanced by less than this share of
    # the poll interval. Generous: a live stream that drifts a little is fine,
    # one that moves a fraction of a second in 15 is not watching.
    WATCH_STALL_RATIO = 0.25

    # Probe: report the player, and resume it if it is paused or ended.
    _WATCH_RESUME_JS = """() => {
        const v = document.querySelector('video');
        if (!v) return {video: false};
        let live = null;
        try { if (v.seekable.length)
                  live = v.seekable.end(v.seekable.length - 1); } catch (e) {}
        const out = {video: true, paused: v.paused, ended: v.ended,
                     t: v.currentTime, ready: v.readyState, live: live};
        if (v.paused || v.ended) {
            if (v.ended) { try { v.currentTime = 0; } catch (e) {} }
            v.muted = true;            // muted playback needs no gesture
            v.play().catch(() => {});
            out.resumed = true;
        }
        return out;
    }"""

    # Has the BROADCAST ended, as opposed to this page pausing? Facebook
    # relabels a finished live and drops the LIVE badge, and the player stops
    # being live-seekable. A watch with no time limit ends when this is true
    # on every page - "stay until the live is over" is the default, not a
    # number of minutes the operator has to guess in advance.
    _WATCH_ENDED_JS = """() => {
        const text = (document.body.innerText || '').toLowerCase();
        const finished = ['this live video has ended', 'live video ended',
                          'the live video has ended', 'video has ended',
                          'this video is no longer available',
                          'ended live video'];
        if (finished.some(phrase => text.includes(phrase))) return true;
        // A live post still showing its LIVE badge is still running.
        const badge = [...document.querySelectorAll('span, div')]
            .some(el => (el.innerText || '').trim().toUpperCase() === 'LIVE');
        if (badge) return false;
        const v = document.querySelector('video');
        if (!v) return false;
        // A finished broadcast becomes an ordinary VOD: it stops being
        // seekable to a moving edge and reports a fixed duration.
        return v.ended === true;
    }"""

    # Recovery for a page that is "playing" but frozen: jump to the live edge
    # and re-issue play(). A stalled live viewer that is minutes behind the
    # broadcast is not watching the broadcast.
    _WATCH_KICK_JS = """() => {
        const v = document.querySelector('video');
        if (!v) return false;
        try {
            if (v.seekable.length) {
                const end = v.seekable.end(v.seekable.length - 1);
                if (end - v.currentTime > 1) v.currentTime = Math.max(0, end - 1);
            }
        } catch (e) {}
        v.muted = true;
        v.play().catch(() => {});
        return true;
    }"""

    # Facebook's own live viewer figure, straight off the player. It is an
    # aggregate it recomputes on its own interval, so it never equals the
    # number of pages open - reading it here is the only way to see both
    # numbers at once instead of guessing which one is wrong.
    _WATCH_VIEWERS_JS = """() => {
        for (const el of document.querySelectorAll('[aria-label]')) {
            const a = el.getAttribute('aria-label') || '';
            if (!/currently watching/i.test(a)) continue;
            const m = a.match(/([\\d.,]+\\s*[KMB]?)\\s+(?:people|person)/i);
            if (m) return m[1].trim();
        }
        return null;
    }"""

    async def _facebook_viewer_count(self) -> str | None:
        """What Facebook publicly says is watching, or None if it shows no count."""
        for auto in list(self._watch_autos.values()):
            try:
                got = await auto.page.evaluate(self._WATCH_VIEWERS_JS)
            except Exception:
                continue
            if got:
                return got
        return None

    def _pages_that_fit(self) -> int | None:
        """How many watch pages this machine's free RAM can hold, or None when
        it cannot be measured.

        Opening past that point does not get more viewers - it gets a swapping
        machine where nothing plays and the desktop stops responding.
        """
        try:
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            free_mb = int(status.ullAvailPhys / (1024 * 1024))
        except Exception:
            return None
        usable = max(0, free_mb - self.WATCH_RESERVE_MB)
        return max(1, usable // max(1, self.WATCH_PAGE_MB))

    @staticmethod
    def _desktop_size() -> tuple[int, int] | None:
        """The desktop in the units a window is positioned in.

        Not the physical mode: Browser.setWindowBounds speaks the same
        device-independent pixels Windows uses to place windows - 1536x864 on
        a 1920x1080 screen at 125% - and the physical figure put the grid a
        quarter of a screen too wide, so every window was clamped back to the
        corner and the tiles piled up.
        """
        try:
            import ctypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            dc = user32.GetDC(0)
            try:
                width = int(gdi32.GetDeviceCaps(dc, 118))   # DESKTOPHORZRES
                height = int(gdi32.GetDeviceCaps(dc, 117))  # DESKTOPVERTRES
            finally:
                user32.ReleaseDC(0, dc)
            return (width, height) if width > 0 and height > 0 else None
        except Exception:
            return None

    async def _tile_watch_windows(self):
        """Lay the visible watch windows out as a grid filling the screen.

        Playwright cannot move a window, so this goes through CDP:
        Browser.getWindowForTarget for the window behind each page, then
        Browser.setWindowBounds. Headless modes have no windows to place, so
        the caller only runs this for the visible mode.

        The grid is the squarest one that holds every page - 11 pages become
        4 columns by 3 rows - and the screen size comes from the browser
        itself, so nothing here needs the UI toolkit or a guess about DPI.
        """
        autos = list(self._watch_autos.items())
        if not autos:
            return
        first = autos[0][1]
        try:
            sw, sh, sx, sy = await first.page.evaluate(
                "() => [screen.availWidth, screen.availHeight,"
                " screen.availLeft || 0, screen.availTop || 0]")
        except Exception as e:
            self.log(f"  ⚠️  Could not read the screen size, leaving windows "
                     f"where they are: {str(e)[:80]}")
            return

        # Ten to a row, square tiles, a gap between them - the layout in the
        # icon the operator drew, not a screen chopped into whatever
        # rectangles happened to fit. Square means one side governs: take the
        # smaller of "a tenth of the width" and "one row's share of the
        # height", and the leftover becomes the margin the grid is centred in.
        # What the page reports as its screen cannot be trusted here: a
        # context opened with a storage state came back saying 1280x800 while
        # devicePixelRatio was 0.25, which would put the whole grid inside a
        # corner of the real screen. The desktop size comes from Windows
        # instead, converted into the browser's own units by the same scale
        # factor the browser was launched with - the two numbers then agree
        # by construction rather than by hope.
        native = self._desktop_size()
        if native:
            sw = int(native[0] / self.WATCH_GRID_SCALE)
            sh = int(native[1] / self.WATCH_GRID_SCALE)
            sx = sy = 0

        count = len(autos)
        cols = max(1, self.WATCH_GRID_COLS)
        rows = max(1, math.ceil(count / cols))
        gap = self.WATCH_GRID_GAP
        side = max(1, min((sw - gap * (cols + 1)) // cols,
                          (sh - gap * (rows + 1)) // rows))
        cell_w = cell_h = int(side)
        # Centre the block AND keep a margin at the edges: never less than one
        # gutter on the left, right, top and bottom, so the outer windows are
        # not flush against the screen edge while the inner ones have space.
        pad_x = max(gap, int((sw - (cols * cell_w + gap * (cols - 1))) // 2))
        pad_y = max(gap, int((sh - (rows * cell_h + gap * (rows - 1))) // 2))
        placed = 0
        for i, (name, auto) in enumerate(autos):
            left = int(sx + pad_x + (i % cols) * (cell_w + gap))
            top = int(sy + pad_y + (i // cols) * (cell_h + gap))
            try:
                cdp = await auto.page.context.new_cdp_session(auto.page)
                info = await cdp.send("Browser.getWindowForTarget")
                await cdp.send("Browser.setWindowBounds", {
                    "windowId": info["windowId"],
                    "bounds": {"left": left, "top": top,
                               "width": cell_w, "height": cell_h,
                               "windowState": "normal"}})
                await cdp.detach()
                placed += 1
            except Exception as e:
                self.log(f"  ⚠️  Could not place '{name}': {str(e)[:80]}")
        self.log(f"  ▦ Tiled {placed}/{count} window(s) as {cols}x{rows} "
                 f"on {sw}x{sh} ({cell_w}x{cell_h} each)")

    async def _finished_lives(self) -> set:
        """The URLs whose broadcast has ended, judged per live.

        Every page on a live has to agree before that live counts as over.
        One page that lost its player, hit a gate or cannot be asked is a
        broken viewer, not proof the broadcast ended - and a second live
        running in the same browser must not be ended by the first one
        finishing, which is why the verdict is per URL and not per fleet.
        """
        autos = getattr(self, "_watch_autos", None) or {}
        urls = getattr(self, "_watch_urls", None) or {}
        if not autos:
            return set()
        per_live: dict = {}
        for name, auto in list(autos.items()):
            url = urls.get(name)
            if not url:
                continue
            try:
                ended = bool(await auto.page.evaluate(self._WATCH_ENDED_JS))
            except Exception:
                ended = False     # could not ask: assume it is still running
            per_live.setdefault(url, []).append(ended)
        return {url for url, verdicts in per_live.items() if verdicts and all(verdicts)}

    async def _keep_watching(self, url: str, deadline: float | None = None):
        """Keep every watch page playing until the watch is stopped.

        A page left alone does not keep watching, and it fails in two different
        ways. Facebook PAUSES a video when a live stream cuts over, when a VOD
        ends, and when the player loses the stream. Separately, a page under
        load STALLS: the media buffer runs dry, readyState drops, currentTime
        stops moving - and `paused` stays false the whole time. Measured on a
        9-profile live watch: 3-4 pages frozen inside 30s, all of them still
        reporting paused=false. A check that only looks at `paused` calls those
        pages healthy forever, which is the worst outcome: the app says it is
        watching and nothing is.

        So each round does three things: resume anything paused or ended,
        detect a frozen page by comparing currentTime against the previous
        round and kick it back to the live edge (reloading if a kick does not
        take), and reload a page that has lost its player entirely (a gate or a
        navigation away).

        deadline is an event-loop timestamp; reaching it stops the whole watch
        through the normal stop command. None means watch the whole broadcast:
        the keeper then ends the watch when the live itself is over, which is
        the default - an operator cannot know in advance how long a live runs.
        """
        loop = asyncio.get_running_loop()
        last_t: dict[str, float] = {}
        stalls: dict[str, int] = {}
        rounds = 0
        next_beat = loop.time() + random.uniform(self.WATCH_BEAT_MIN_SECONDS,
                                                 self.WATCH_BEAT_MAX_SECONDS)
        try:
            while True:
                slept = random.uniform(self.WATCH_POLL_MIN_SECONDS,
                                       self.WATCH_POLL_MAX_SECONDS)
                await asyncio.sleep(slept)
                if not self._watch_autos:
                    return
                if deadline is not None and loop.time() >= deadline:
                    self.log("👁 Watch: time limit reached - stopping.")
                    self.cmd_queue.put({"type": "stop_watch"})
                    return
                if deadline is None:
                    finished = await self._finished_lives()
                    if finished:
                        done = [n for n, u in self._watch_urls.items()
                                if u in finished]
                        self.log(f"👁 Watch: a live has ended - closing "
                                 f"{len(done)} page(s) on it.")
                        await self._close_watch_pages(done)
                        if not self._watch_autos:
                            self.log("👁 Watch: no live left to watch - "
                                     "stopping.")
                            self.cmd_queue.put({"type": "stop_watch"})
                            return
                rounds += 1
                resumed, reloaded, kicked, playing = [], [], [], 0
                for name, auto in list(self._watch_autos.items()):
                    try:
                        r = await auto.page.evaluate(self._WATCH_RESUME_JS)
                    except Exception:
                        continue          # page closing or mid-navigation
                    if not r.get("video"):
                        last_t.pop(name, None)
                        stalls.pop(name, None)
                        try:
                            await auto.page.goto(self._watch_urls.get(name, url),
                                                 wait_until="domcontentloaded",
                                                 timeout=45000)
                            reloaded.append(name)
                        except Exception:
                            pass
                        continue
                    now_t = r.get("t") or 0.0
                    if r.get("resumed"):
                        resumed.append(name)
                        stalls[name] = 0
                        last_t[name] = now_t
                        continue
                    advanced = now_t - last_t.get(name, now_t)
                    last_t[name] = now_t
                    frozen = (name in stalls or rounds > 1) and \
                        advanced < slept * self.WATCH_STALL_RATIO
                    if not frozen:
                        stalls[name] = 0
                        playing += 1
                        continue
                    stalls[name] = stalls.get(name, 0) + 1
                    if stalls[name] == 1:
                        try:
                            await auto.page.evaluate(self._WATCH_KICK_JS)
                            kicked.append(name)
                        except Exception:
                            pass
                    else:
                        # A kick did not take: the renderer is wedged, so
                        # rebuild the page rather than keep a dead viewer.
                        try:
                            await auto.page.goto(self._watch_urls.get(name, url),
                                                 wait_until="domcontentloaded",
                                                 timeout=45000)
                            reloaded.append(name)
                            stalls[name] = 0
                            last_t.pop(name, None)
                        except Exception:
                            pass
                if resumed:
                    self.log(f"  👁 resumed {len(resumed)} paused page(s): "
                             f"{', '.join(resumed[:4])}"
                             + (" ..." if len(resumed) > 4 else ""))
                if kicked:
                    self.log(f"  👁 stalled, seeking to live edge: "
                             f"{len(kicked)} page(s): {', '.join(kicked[:4])}"
                             + (" ..." if len(kicked) > 4 else ""))
                if reloaded:
                    self.log(f"  👁 reloaded {len(reloaded)} page(s) that lost "
                             f"the player or stayed frozen: "
                             f"{', '.join(reloaded[:4])}"
                             + (" ..." if len(reloaded) > 4 else ""))
                # A quiet heartbeat, so a long watch is visibly alive
                # without flooding the log. Fires on a randomised 1.5-3 min
                # gap rather than a fixed count of rounds.
                if loop.time() >= next_beat:
                    next_beat = loop.time() + random.uniform(
                        self.WATCH_BEAT_MIN_SECONDS, self.WATCH_BEAT_MAX_SECONDS)
                    left = ""
                    if deadline is not None:
                        mins = max(0.0, (deadline - loop.time()) / 60.0)
                        left = f", {mins:.0f} min left"
                    fb = await self._facebook_viewer_count()
                    # Deliberately side by side. They measure different things
                    # and will not match: the first is these pages, the second
                    # is Facebook's own aggregate, which lags and dedupes.
                    shown = (f"; Facebook shows {fb} watching" if fb
                             else "; Facebook shows no viewer count")
                    self.log(f"  👁 Watch: {playing}/{len(self._watch_autos)} "
                             f"page(s) actually playing{left}{shown}")
        except asyncio.CancelledError:
            raise

    async def _do_watch(self, url: str, minutes: float | None = None,
                        profile_names: list[str] | None = None):
        """Open one window per active profile on `url` and keep them playing.

        Reuses the batch primitives - storage-state extraction (cached where
        possible) and init_from_storage on a single shared browser - but
        request interception is off entirely so media segments never queue
        behind this process, and nothing is closed afterwards. "Active" is the
        logged-in set (status='ok'), the same source the UI filters on.
        profile_names narrows the candidates; the 'ok' filter still applies
        on top, so an explicit request can never open a dead session.

        The windows follow the "Browser mode" setting, exactly like a queue
        run: on the default hidden mode the pages load and play with no Brave
        window on screen. Pick "Visible windows" to watch them yourself.

        minutes bounds the run; None means until the Stop button. Each page is
        verified to be really playing before it is counted, because a page that
        merely loaded is not a viewer.
        """
        from src.core.facebook_automation import (FacebookAutomation,
                                                   CHROME_PATH, WATCH_FLAGS,
                                                   LOGIN_GATE_JS)
        from src.storage import state_cache

        # Only the profiles about to be reused are closed. Closing the whole
        # watch here is what took an unrelated live down with it: one account
        # watches one live at a time, but the other accounts' windows are
        # nobody else's business.

        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            self.log("Watch: URL must start with http:// or https://")
            return

        # Every profile asked for takes part. A stored status is a verdict
        # from an earlier run, not the state of the session now - the same
        # rule the queue follows - so a profile the roster calls signed out is
        # still opened and judged by whether its page actually plays.
        ok = db.logged_in_profiles()
        profiles = list(profile_names or cfg.list_profiles_for_browser())
        unproven = [p for p in profiles if p not in ok]
        if unproven:
            self.log(f"Watch: {len(unproven)} profile(s) were not logged in at "
                     f"their last check - opening them anyway")
        if not profiles:
            self.log("Watch: no profiles to open.")
            return

        room = self._pages_that_fit()
        if room is not None and len(profiles) > room:
            self.log(f"Watch: RAM fits about {room} page(s); opening the first "
                     f"{room} of {len(profiles)} so the machine keeps up")
            profiles = profiles[:room]

        how_long = (f"for {minutes:.0f} min" if minutes
                    else "until the live ends (or you press Stop)")
        self.log(f"👁 Watch: opening {len(profiles)} active profile(s) on {url} "
                 f"({how_long})")

        states: dict = {}
        for i, p in enumerate(profiles):
            st = state_cache.load_state(p)
            if st is None:
                bp = cfg.get_profile_path(p)
                if bp:
                    temp = self._create_temp_automation()
                    try:
                        st = await temp.extract_storage_state(bp, skip_navigation=True)
                        if st:
                            state_cache.save_state(p, st)
                    except Exception as e:
                        self.log(f"  ⚠️  extract failed '{p}': {e}")
                        st = None
                    finally:
                        try:
                            await temp.quit()
                        except Exception:
                            pass
                    if i < len(profiles) - 1:
                        await asyncio.sleep(0.5)   # release singleton lock
            states[p] = st

        active = [p for p in profiles if states.get(p) is not None]
        if not active:
            self.log("Watch: no usable sessions - nothing opened.")
            return

        mode, launch_headless, launch_args = \
            self._browser_launch_mode(SMALL_VIEWPORT, autoplay=True,
                                      flags=WATCH_FLAGS)
        if mode == "visible":
            # Shrink the browser's own unit so a 10x10 cell clears Chromium's
            # minimum window width; without this every window comes back
            # clamped and the grid is a pile.
            launch_args = [*launch_args,
                           f"--force-device-scale-factor={self.WATCH_GRID_SCALE:g}"]
        await self._close_watch_pages(active)

        if not getattr(self, "_watch_browser", None):
            self._watch_pw = await async_playwright().start()
            self._watch_browser = await self._launch_browser(
                self._watch_pw, launch_headless, launch_args)
        self._watch_autos = getattr(self, "_watch_autos", {}) or {}
        self._watch_urls = getattr(self, "_watch_urls", {}) or {}

        # Opening all of them at once does not work: 46 pages loading and 46
        # decoders starting together took 198 s to open and left 2 playing,
        # with the keeper reloading twenty of them afterwards. Opening a few
        # at a time is fast and keeps the players alive, and joining late
        # costs nothing because every page is pulled to the live edge below -
        # the edge is where the broadcast is now, whatever time a page opened.
        sem = asyncio.Semaphore(min(max(1, len(active)), self.WATCH_OPEN_AT_ONCE))

        verdicts: dict[str, str] = {}

        async def _open(profile_name: str):
            async with sem:
                auto = FacebookAutomation(log_callback=self.log, debug=self._debug)
                await auto.init_from_storage(self._watch_browser,
                                             states[profile_name],
                                             viewport=SMALL_VIEWPORT,
                                             block_resources=False,
                                             no_viewport=(mode == "visible"))
                self._watch_autos[profile_name] = auto
                self._watch_urls[profile_name] = url
                try:
                    await auto.page.goto(url, wait_until="domcontentloaded",
                                         timeout=45000)
                except Exception as e:
                    verdicts[profile_name] = "navigation failed"
                    self.log(f"  ⚠️  '{profile_name}' navigation failed: {e}")
                    return
                verdicts[profile_name] = await self._verify_watching(
                    auto, profile_name)

        await asyncio.gather(*(_open(p) for p in active), return_exceptions=True)

        # Everyone to the same moment of the broadcast. Pages opened in
        # groups, so the first ones have been playing while the last were
        # still loading; the live edge is where the stream is NOW, so one
        # pass over every page puts the whole fleet on the same content.
        aligned = 0
        for auto in list(self._watch_autos.values()):
            try:
                if await auto.page.evaluate(self._WATCH_KICK_JS):
                    aligned += 1
            except Exception:
                pass
        if aligned:
            self.log(f"  ⇥ {aligned} page(s) moved to the live edge")

        watching = [n for n, v in verdicts.items() if v == "playing"]
        broken = {n: v for n, v in verdicts.items() if v != "playing"}
        where = ("hidden - no Brave window on screen" if mode != "visible"
                 else "on screen")
        # Opening the pages is not watching them: without this, the first
        # pause or stall ends every view while the pages sit there looking fine.
        if mode == "visible" and self._watch_autos:
            await self._tile_watch_windows()
        deadline = None
        if minutes:
            deadline = asyncio.get_running_loop().time() + minutes * 60
        self._watch_keeper = asyncio.create_task(
            self._keep_watching(url, deadline))
        for name, why in broken.items():
            self.log(f"  ⚠️  '{name}' opened but is NOT watching: {why}")
        # "at open" matters: this is one snapshot taken as the pages loaded,
        # not live status. The keeper's heartbeat is the running number, and
        # neither one is Facebook's published viewer count - that is Facebook's
        # own aggregate and it will not match the page count exactly.
        self.log(f"👁 Watch started: {len(watching)}/{len(self._watch_autos)} "
                 f"page(s) playing at open [{mode}, {where}], {how_long}. "
                 f"Live count follows every 1.5-3 min.")

    # How many watch pages load at the same time. Past this the machine
    # starves its own players: the pages open but the video never starts.
    WATCH_OPEN_AT_ONCE = 8

    # What one watching page costs in RAM, measured on this fleet: a Chromium
    # renderer decoding a live, with images off and a 96 MB heap cap. The
    # watch refuses to open more pages than the machine can hold, because a
    # machine in swap plays no video at all - 46 visible pages took 14 minutes
    # to open and 22 of them ever played.
    WATCH_PAGE_MB = 180
    # Never eat the last of the machine: leave this much for Windows and the
    # app itself.
    WATCH_RESERVE_MB = 2048

    # The visible watch lays its windows out ten to a row, as many rows as it
    # takes. Chromium refuses a window under about 515 of its own units wide
    # and a tenth of a screen is far below that, so the watch browser is
    # launched with a scale factor that makes its unit smaller than a screen
    # pixel - the same trick the login grid uses.
    WATCH_GRID_COLS = 10
    WATCH_GRID_SCALE = 0.25
    # The gutter between tiles, in the browser's own units. Without it the
    # windows touch and read as one sheet instead of a grid.
    WATCH_GRID_GAP = 24

    # How long a freshly opened page gets to mount a player, and how long its
    # currentTime is sampled to prove the player is really running.
    WATCH_VERIFY_TIMEOUT_MS = 25000
    WATCH_VERIFY_SAMPLE_SECONDS = 3

    # ── Session upkeep ───────────────────────────────────────────────────
    #
    # Facebook expires a session that goes cold, and the fleet lost six in one
    # night that way. The sweep does two jobs on a timer: it keeps live
    # sessions warm by actually using them, and it recovers the ones already
    # lost.
    #
    # Recovery differs by reason, because the two are not the same problem.
    # An expired session is ours to fix - the password still works, so log in
    # again. A checkpoint is Facebook demanding a human (an ID photo, a code,
    # "confirm it's you"); it has no password form at all, so a login attempt
    # cannot clear it and repeating one is the signal that turns a checkpoint
    # into a permanent disable. Those are only RE-CHECKED, on a long cooldown,
    # because Facebook does lift them on its own - and the moment one lifts,
    # the account goes straight back to active.
    SWEEP_MINUTES_DEFAULT = 30
    RECHECK_GATED_HOURS = 6
    GATED_REASONS = ("checkpoint or verification required",
                     "email confirmation required")

    async def _session_sweep_loop(self):
        """Keep sessions warm and recover lost ones, forever."""
        while True:
            minutes = float(cfg.get_setting("session_sweep_minutes",
                                            self.SWEEP_MINUTES_DEFAULT) or 0)
            if minutes <= 0:
                return                       # switched off
            # Jittered: a sweep landing on the same minute forever is a
            # pattern, and nothing here needs an exact cadence.
            await asyncio.sleep(random.uniform(minutes * 45, minutes * 75))
            if not cfg.get_setting("session_keepalive", True):
                continue
            if self._batch_running or self._watch_autos:
                continue                     # never compete with real work
            try:
                await self._session_sweep()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.log(f"Session sweep failed: {str(e)[:120]}")

    async def _session_sweep(self):
        """One pass: warm the live sessions, then recover the lost ones."""
        from src.core.facebook_automation import (FacebookAutomation,
                                                  CHROME_PATH, WATCH_FLAGS)
        from src.storage import state_cache

        ok = db.logged_in_profiles()
        active = [p for p in cfg.list_profiles()
                  if p in ok and state_cache.load_state(p) is not None]
        warmed = expired = 0
        if active:
            pw = await async_playwright().start()
            browser = None
            try:
                browser = await self._launch_browser(
                    pw, False, ["--window-size=1024,768", *WATCH_FLAGS,
                                "--headless=new"])
                for name in active:
                    result = await self._keepalive_profile(
                        browser, name, state_cache)
                    if result is True:
                        warmed += 1
                    elif result is False:
                        expired += 1
            finally:
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:
                        pass
                try:
                    await pw.stop()
                except Exception:
                    pass
        if warmed or expired:
            self.log(f"♻ Session sweep: {warmed} kept warm, "
                     f"{expired} found expired")
        await self._recover_lost_sessions()

    async def _keepalive_profile(self, browser, profile_name: str,
                                 state_cache) -> bool | None:
        """Use the session so Facebook keeps it, and re-save what comes back.

        Returns True when the session is live, False when Facebook has taken
        it away, None when the check was inconclusive and must change nothing.
        """
        from src.core.facebook_automation import FacebookAutomation

        state = state_cache.load_state(profile_name)
        if state is None:
            return None
        auto = FacebookAutomation(log_callback=lambda m: None)
        try:
            await auto.init_from_storage(browser, state, block_resources=False)
            await auto.page.goto("https://www.facebook.com/",
                                 wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(random.uniform(2, 5))
            if await self._session_is_live(auto):
                # Facebook reissues cookies on use; storing them back is what
                # actually pushes the expiry out rather than just reading it.
                try:
                    state_cache.save_state(profile_name,
                                           await auto.context.storage_state())
                except Exception:
                    pass
                return True
            status = await auto._classify_account_access()
            if status in ("unreachable", "unknown"):
                return None          # a blip says nothing about the account
            await self._record_and_publish(profile_name, False, status)
            state_cache.invalidate(profile_name)
            return False
        except Exception:
            return None
        finally:
            try:
                await auto.close_context()
            except Exception:
                pass

    async def _recover_lost_sessions(self):
        """Re-login what can be re-logged in; re-check what only Facebook can."""
        if not cfg.get_setting("auto_relogin", True):
            return
        relogin, recheck = [], []
        for account in db.list_accounts(include_disabled=False):
            name = account.get("linked_profile") or ""
            if not name or account.get("status") == "ok":
                continue
            reason = (account.get("status_reason") or "").strip().lower()
            if reason in self.RELOGIN_REASONS:
                relogin.append(name)
            elif reason in self.GATED_REASONS:
                recheck.append(name)

        for name in relogin:
            if self._relogin_allowed(name):
                await self._relogin_profile(name)

        if not hasattr(self, "_recheck_last"):
            self._recheck_last = {}
        cooldown = self.RECHECK_GATED_HOURS * 3600
        for name in recheck:
            if time.monotonic() - self._recheck_last.get(name, 0.0) < cooldown:
                continue
            self._recheck_last[name] = time.monotonic()
            await self._recheck_gated_profile(name)

    async def _recheck_gated_profile(self, profile_name: str):
        """Has Facebook lifted this account's checkpoint yet?

        Opens the profile and looks - no login attempt, no form filling.
        Nothing here can clear a checkpoint, and pretending otherwise is how
        an account gets disabled instead of released. If the gate is gone the
        account returns to active immediately.
        """
        from src.core.facebook_automation import FacebookAutomation

        brave_path = cfg.get_profile_path(profile_name)
        if not brave_path:
            return
        auto = FacebookAutomation(log_callback=lambda m: None)
        try:
            state, logged_in = await auto.extract_storage_state(
                brave_path, return_logged_in=True)
            status = getattr(auto, "last_account_status", "unknown")
            if logged_in:
                from src.storage import state_cache
                if state:
                    state_cache.save_state(profile_name, state)
                await self._record_and_publish(profile_name, True, "logged_in")
                self.log(f"  ✓ '{profile_name}': Facebook lifted the gate - "
                         f"active again")
            elif status not in ("unreachable", "unknown"):
                await self._record_and_publish(profile_name, False, status)
        except Exception as e:
            self.log(f"  ⚠️  re-check of '{profile_name}' failed: {str(e)[:90]}")
        finally:
            try:
                await auto.quit()
            except Exception:
                pass

    async def _record_and_publish(self, profile_name: str, logged_in: bool,
                                  reason: str = "") -> bool:
        """Record a login verdict and mirror it to the sheet, together.

        The one place that writes a verdict. Recording and publishing were
        separate, and one caller - the batch demotion - only ever did the
        first, so a profile could go inactive in the database while the sheet
        still showed it LOGGED IN. That is exactly how the app came to report
        five active profiles against two on the sheet.

        Returns whether anything was recorded; an inconclusive check writes
        nothing and publishes nothing.
        """
        recorded = db.record_login_check(profile_name, logged_in, reason)
        if recorded:
            await self._push_sheet_status(profile_name)
        return recorded

    async def _push_sheet_status(self, profile_name: str):
        """Mirror one profile's recorded account status to the roster sheet.

        The database has just been written, so this only carries that verdict
        across - the sheet cannot end up saying something the database does
        not hold. Blocking network I/O, so it runs off the event loop, and it
        is best-effort throughout: an unreachable or unconfigured sheet must
        never stall or fail a watch.
        """
        from src.storage import sheet_status
        account = db.account_for_profile(profile_name)
        username = (account or {}).get("username") or ""
        if not username:
            return
        try:
            text = await asyncio.to_thread(
                sheet_status.push_account_status, username)
        except Exception as e:
            # Offline is one fact about the PC, not one fact per account: a
            # DNS failure printed urllib3's three nested exceptions for every
            # profile in the run, hundreds of identical lines that said only
            # "no network". Say it once per run, short, and carry on - the
            # database already holds the verdict and the sheet is a mirror.
            reason = sheet_reason(e)
            if reason != getattr(self, "_sheet_push_error", None):
                self._sheet_push_error = reason
                self.log(f"  ⚠️  sheet not updated ({reason}) - "
                         f"the verdicts are recorded locally")
            return
        self._sheet_push_error = None
        if text:
            self.log(f"  ✓ sheet updated: {username} → {text}")

    async def _verify_watching(self, auto, profile_name: str) -> str:
        """'playing', or the reason this page is not a viewer.

        page.goto() returning proves a document loaded and nothing more: a
        login wall, an age gate and a dead player all return 200. A view only
        exists if a <video> is on the page and its currentTime is moving, so
        that is what this measures.
        """
        from src.core.facebook_automation import LOGIN_GATE_JS
        try:
            gated = await auto.page.evaluate(LOGIN_GATE_JS)
        except Exception:
            gated = False
        if gated:
            # A gate during a watch is the same evidence a login check acts
            # on, so it goes through the same classifier and the same database
            # rule: 'disabled' for a disabled account, the reason for anything
            # else, nothing at all for 'unreachable'. Without this the watch
            # saw the dead session, said so once, and threw the verdict away -
            # the profile stayed 'ok' and every later watch opened it again.
            status = await auto._classify_account_access(auto.page)
            recorded = await self._record_and_publish(profile_name, False,
                                                      status)
            if status == "disabled_or_suspended":
                return ("ACCOUNT DISABLED by Facebook"
                        + (" - marked disabled, dropped from active"
                           if recorded else ""))
            why = status.replace("_", " ")
            return (f"login gate: {why}"
                    + (" - dropped from active" if recorded else ""))
        try:
            await auto.page.wait_for_selector(
                "video", timeout=self.WATCH_VERIFY_TIMEOUT_MS)
        except Exception:
            return "no video player on the page"
        sample = "() => { const v = document.querySelector('video'); " \
                 "return v ? v.currentTime : null; }"
        try:
            first = await auto.page.evaluate(sample)
            await asyncio.sleep(self.WATCH_VERIFY_SAMPLE_SECONDS)
            second = await auto.page.evaluate(sample)
        except Exception as e:
            return f"player probe failed: {e}"
        if first is None or second is None:
            return "player disappeared"
        if second - first < 0.5:
            # One nudge: autoplay can still be held back on a page that only
            # just finished loading.
            try:
                await auto.page.evaluate(self._WATCH_KICK_JS)
                await asyncio.sleep(self.WATCH_VERIFY_SAMPLE_SECONDS)
                third = await auto.page.evaluate(sample)
            except Exception:
                third = second
            if (third or 0) - second < 0.5:
                return "video is frozen (loaded but not advancing)"
        self.log(f"  👁 watching '{profile_name}'")
        return "playing"

    async def _close_watch_pages(self, names) -> int:
        """Close the watch pages of these profiles only.

        A profile has one session, so it can be on one live at a time and a
        new watch has to take its page back. Every other page stays open -
        that is the difference between starting a second live and ending the
        first.
        """
        autos = getattr(self, "_watch_autos", None) or {}
        urls = getattr(self, "_watch_urls", None) or {}
        closed = 0
        for name in list(names):
            auto = autos.pop(name, None)
            urls.pop(name, None)
            if auto is None:
                continue
            try:
                await auto.close_context()
            except Exception:
                pass
            closed += 1
        if closed:
            self.log(f"👁 Watch: {closed} page(s) moved to the new live")
        return closed

    async def _stop_watch(self):
        """Close every live-watch window and its browser, if any."""
        keeper = getattr(self, "_watch_keeper", None)
        if keeper is not None:
            keeper.cancel()
            try:
                await keeper
            except (asyncio.CancelledError, Exception):
                pass
            self._watch_keeper = None
        autos = getattr(self, "_watch_autos", {})
        if autos:
            self.log(f"👁 Watch: closing {len(autos)} window(s)...")
        for auto in list(autos.values()):
            try:
                await auto.quit()
            except Exception:
                pass
        self._watch_autos = {}
        self._watch_urls = {}
        if getattr(self, "_watch_browser", None):
            try:
                await self._watch_browser.close()
            except Exception:
                pass
            self._watch_browser = None
        if getattr(self, "_watch_pw", None):
            try:
                await self._watch_pw.stop()
            except Exception:
                pass
            self._watch_pw = None

    def _detect_gender_from_name(self, name: str) -> str:
        """Detect gender from profile name using Groq AI.
        
        Returns: "male", "female", or "unknown"
        """
        if not name or not name.strip():
            self.log(f"  Gender detection: Empty name provided")
            return "unknown"
            
        name = name.strip()
        
        # Skip Groq API for non-name inputs (numbers, single chars, Brave profile names)
        if len(name) <= 2 or name.isdigit():
            self.log(f"  Gender detection: '{name}' is not a real name, using fallback")
            return self._detect_gender_from_name_fallback(name)

        # No key configured: a Groq call can only fail here, so skip straight
        # to the local heuristic instead of one doomed request per profile.
        if not GROQ_API_KEY:
            return self._detect_gender_from_name_fallback(name)

        self.log(f"  Gender detection: Querying Groq for '{name}'...")
        
        try:
            client = Groq(api_key=GROQ_API_KEY)
            chat = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a gender classifier. Given a person's full name, "
                            "determine if it is a male or female name. "
                            "Consider Filipino, Asian, Western, and international names. "
                            "Reply with ONLY one word: 'male' or 'female'. "
                            "Do not add any explanation."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"What is the gender of this name: {name}",
                    },
                ],
                temperature=0,
                max_tokens=10,
            )
            answer = chat.choices[0].message.content.strip().lower()
            self.log(f"  Gender detection: Groq returned '{answer}' for '{name}'")
            
            # Robust parsing - accept "male" or "female" anywhere in response
            if "male" in answer and "female" not in answer:
                return "male"
            elif "female" in answer:
                return "female"
            else:
                self.log(f"  Gender detection: Unexpected Groq response '{answer}', using fallback")
                return self._detect_gender_from_name_fallback(name)
                
        except Exception as e:
            self.log(f"  Gender detection: Groq API failed ({e}), falling back to local detection")
            return self._detect_gender_from_name_fallback(name)

    def _detect_gender_from_name_fallback(self, name: str) -> str:
        """Fallback gender detection using hardcoded Filipino name lists."""
        name_lower = name.lower()
        
        male_names = [
            "juan", "jose", "pedro", "antonio", "manuel", "francisco", "miguel", "carlos",
            "ricardo", "ramon", "fernando", "luis", "eduardo", "roberto", "rafael", "sergio",
            "daniel", "alfredo", "rodrigo", "enrique", "salvador", "raul", "emilio", "cesar",
            "mario", "oscar", "victor", "javier", "diego", "ruben", "jorge",
            "pablo", "marco", "leonardo", "alejandro", "andres", "santiago", "felipe",
            "joshua", "john", "james", "mark", "paul", "michael", "david", "christian",
            "joseph", "matthew", "ryan", "kevin", "kenneth", "gerald", "jerome", "jerico",
            "jayson", "jaymar", "jomar", "jerson", "jeric", "justine", "joselito",
            "jun", "nonoy", "noel", "rey", "roy", "roel", "ronnie", "raffy",
            "jojo", "boyet", "dodong", "totoy", "toto", "bong", "dong",
            "paolo", "lorenzo", "mateo", "gabriel", "sebastian", "nicolas",
            "adrian", "lucas", "martin", "julian", "dante",
            "carlo", "rico", "dino", "nino", "lito", "pepito", "juanito", "carlito",
            "ernesto", "alberto", "jerwin", "erwin", "darwin", "marvin", "melvin",
            "kelvin", "calvin", "alvin", "arvin", "edwin", "sherwin",
            "miko", "nico", "chico", "paco", "kiko", "jiro",
            "bryan", "brian", "jordan", "brandon", "jason", "nelson", "wilson",
            "edison", "emerson", "aldrin", "marlon", "simon",
            "patrick", "frederick", "roderick", "derrick", "erick", "maverick",
            "lance", "vince", "bruce", "alex", "max", "felix", "rex",
            "ian", "evan", "neil", "kyle", "jake", "carl", "nick",
            "gian", "xian", "kian", "renz", "kenzo", "jude", "zeke",
            "andre", "andrei", "mike", "mikey", "ricky",
        ]
        
        female_names = [
            "maria", "ana", "rosa", "luz", "carmen", "elena", "josefa", "teresa",
            "gloria", "socorro", "esperanza", "mercedes", "concepcion", "lourdes",
            "milagros", "rosario", "pilar", "dolores", "victoria", "trinidad", "paz",
            "mary", "marie", "mariel", "maricel", "maribel", "marites", "marissa",
            "angel", "angela", "angelica", "angelina", "angie",
            "grace", "graciela", "gretchen",
            "christine", "christina", "kristina", "krista", "kristine", "krishia",
            "catherine", "katherine", "katrina", "kathryn", "kate", "kaye",
            "michelle", "mitchelle",
            "jasmine", "jasmin", "jazmin",
            "patricia", "tricia", "trisha",
            "jennifer", "jenny",
            "stephanie", "steffi",
            "diane", "diana", "dina",
            "nancy", "nanette",
            "sarah", "sara", "czarina", "zarina",
            "inday", "neneng", "nene", "daisy", "ruby", "pearl",
            "cherry", "precious", "princess", "divine", "heaven", "faith",
            "hope", "charity", "joy", "love", "peace",
            "isabela", "sofia", "valentina", "lucia", "camila", "natalia",
            "gabriela", "daniela", "valeria", "adriana", "carolina", "mariana", "juliana",
            "anna", "lina", "tina", "gina", "mina", "rina",
            "jessica", "melissa", "vanessa", "clarissa", "marissa", "carissa",
            "amanda", "miranda", "linda", "belinda", "melinda",
            "rowena", "lorena", "serena", "elena", "selena",
        ]
        
        name_words = name_lower.split()
        
        for male_name in male_names:
            if male_name in name_words:
                return "male"
        
        for female_name in female_names:
            if female_name in name_words:
                return "female"
        
        sorted_male = sorted(male_names, key=len, reverse=True)
        for male_name in sorted_male:
            if male_name in name_lower and len(male_name) > 3:
                return "male"
        
        sorted_female = sorted(female_names, key=len, reverse=True)
        for female_name in sorted_female:
            if female_name in name_lower and len(female_name) > 3:
                return "female"
        
        return "unknown"

    def _analyze_friend_connections(self, profiles_data: list[dict], connection_results: list[dict],
                                    profile_names: list[str] = None) -> dict:
        """Analyze friend connections between accounts — local verification + Groq AI summary.

        For N profiles, each should have exactly N-1 friends (every other profile).
        Builds the full friendship matrix locally, then sends to Groq for analysis.

        Args:
            profiles_data: List of dicts with profile_name, facebook_url, gender, friend_count
            connection_results: List of dicts with sender, target, action, success, detail
            profile_names: List of all profile names (used for matrix). If None, extracted from profiles_data.

        Returns:
            dict with keys:
              - all_connected: bool (True if every profile has N-1 friends)
              - per_profile: dict[profile_name] -> {"friends": int, "expected": int, "missing": list[str], "ok": bool}
              - total_pairs: int
              - connected_pairs: int
              - analysis: str (Groq AI text)
        """
        self.log(f"\n🔍 Analyzing friend connections...")

        if not profile_names:
            profile_names = [p["profile_name"] for p in profiles_data]

        n = len(profile_names)
        expected_per_profile = n - 1 if n >= 2 else 0
        expected_pairs = n * (n - 1) // 2

        # ── Build local friendship matrix ─────────────────────
        per_profile = {}
        connected_pairs = 0

        for name in profile_names:
            friends_of = db.get_friend_count_for_profile(name)
            non_friends = db.get_non_friends(name, profile_names)
            missing = [nf for nf in non_friends if nf != name]
            ok = friends_of >= expected_per_profile and len(missing) == 0
            per_profile[name] = {
                "friends": friends_of,
                "expected": expected_per_profile,
                "missing": missing,
                "ok": ok,
            }

        # Count actual connected pairs
        for i, a in enumerate(profile_names):
            for b in profile_names[i + 1:]:
                if db.are_friends(a, b):
                    connected_pairs += 1

        all_connected = connected_pairs >= expected_pairs

        # ── Log per-profile report ────────────────────────────
        self.log(f"\n{'='*60}")
        self.log(f"📊 FRIENDSHIP MATRIX: {connected_pairs}/{expected_pairs} pairs connected")
        self.log(f"{'='*60}")
        for name in profile_names:
            info = per_profile[name]
            status = "✅" if info["ok"] else "❌"
            self.log(f"  {status} {name}: {info['friends']}/{info['expected']} friends"
                     + (f" — MISSING: {', '.join(info['missing'])}" if info["missing"] else ""))

        if all_connected:
            self.log(f"\n🎉 ALL profiles are friends with each other! ({connected_pairs}/{expected_pairs} pairs)")
        else:
            missing_count = expected_pairs - connected_pairs
            missing_profiles = [n for n, info in per_profile.items() if not info["ok"]]
            self.log(f"\n⚠️  {missing_count} pair(s) NOT connected yet: {', '.join(missing_profiles)}")

        self.log(f"{'='*60}")

        # ── Groq AI analysis ──────────────────────────────────
        # No key: skip the call (the local friendship matrix above is
        # authoritative); the existing handler logs and moves on.
        analysis_text = ""
        try:
            if not GROQ_API_KEY:
                raise RuntimeError("GROQ_API_KEY not set — skipping AI analysis")
            client = Groq(api_key=GROQ_API_KEY)

            profile_summary = "\n".join(
                f"- {p['profile_name']}: friends={per_profile.get(p['profile_name'], {}).get('friends', '?')}/{expected_per_profile}, "
                f"gender={p.get('gender', 'unknown')}, "
                f"missing={per_profile.get(p['profile_name'], {}).get('missing', [])}"
                for p in profiles_data
            )

            connection_summary = "\n".join(
                f"- {r['sender']} -> {r['target']}: {r['action']} "
                f"({'OK' if r['success'] else 'FAILED'}) {r.get('detail', '')}"
                for r in connection_results[-100:]  # Last 100 to avoid token limits
            )

            prompt = f"""You are a Facebook account network analyst. Analyze these {n} accounts.

RULE: For {n} profiles, each profile MUST have exactly {expected_per_profile} friends (all other profiles, excluding itself).
Total expected pairs: {expected_pairs}
Currently connected: {connected_pairs}

ACCOUNTS ({n} total):
{profile_summary}

RECENT CONNECTION ACTIONS (last 100):
{connection_summary}

Provide analysis in exactly this format:
1. Network status: {connected_pairs}/{expected_pairs} pairs connected ({connected_pairs*100//max(expected_pairs,1)}%)
2. Profiles still missing friends: [list names or "NONE"]
3. Root cause for failures: [brief reason]
4. Health score: X/100
5. Fix recommendation: [one actionable step]

Be concise. No greeting."""

            chat = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Analyze {n} Facebook profiles with {connected_pairs}/{expected_pairs} friend pairs connected."},
                ],
                temperature=0.3,
                max_tokens=300,
            )

            analysis_text = chat.choices[0].message.content.strip()
            self.log(f"\n🤖 AI ANALYSIS:\n{'='*50}\n{analysis_text}\n{'='*50}")

        except Exception as e:
            self.log(f"  ⚠️  Groq AI analysis failed: {e}")
            analysis_text = f"AI analysis unavailable: {e}"

        return {
            "all_connected": all_connected,
            "per_profile": per_profile,
            "total_pairs": expected_pairs,
            "connected_pairs": connected_pairs,
            "analysis": analysis_text,
        }
