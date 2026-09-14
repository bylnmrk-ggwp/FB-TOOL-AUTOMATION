import asyncio
import gc
import json
import os
import random
import re
import tempfile
import time
import traceback
import urllib.parse
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright, Locator, Page, BrowserContext
from src.storage import config_manager as cfg

from src.core import browser_choice
from src.core import human_input

CHROME_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
BRAVE_USER_DATA = os.environ.get("LOCALAPPDATA", "") + r"\BraveSoftware\Brave-Browser\User Data"


def _close_brave_if_running():
    """Kill any running Brave processes so the profile isn't locked."""
    import subprocess
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "brave.exe", "/T"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _is_profile_locked(profile_path: str) -> bool:
    """Check if a Brave profile directory is locked by examining lock files.
    
    Returns True if the profile appears to be locked/in use.
    """
    try:
        lock_files = ["Singleton", "SingletonLock", "SingletonSocket", "lockfile"]
        for lock_file in lock_files:
            lock_path = os.path.join(profile_path, lock_file)
            if os.path.exists(lock_path):
                # Try to open the lock file - if it fails, profile is locked
                try:
                    with open(lock_path, 'a'):
                        pass
                except (IOError, PermissionError):
                    return True
        return False
    except Exception:
        return False


def _wait_for_profile_unlock(profile_path: str, max_wait: int = 10) -> bool:
    """Wait for a profile to become unlocked.
    
    Args:
        profile_path: Path to the Brave profile directory
        max_wait: Maximum seconds to wait
        
    Returns:
        True if profile became unlocked, False if still locked after timeout
    """
    import time
    for i in range(max_wait):
        if not _is_profile_locked(profile_path):
            return True
        time.sleep(1)
    return False


def fetch_facebook_name_sync(brave_profile_path: str) -> str | None:
    """Launch a temporary headless browser with the Brave profile and fetch the Facebook name.
    
    This is a synchronous (blocking) helper for use in UI code.
    Returns the Facebook display name or None if failed/not logged in.
    """
    import asyncio as _asyncio
    import sys as _sys
    
    def _log(msg):
        print(f"[fetch_fb_name] {msg}", file=_sys.stderr, flush=True)
    
    _log(f"Starting fetch for: {brave_profile_path}")
    
    # Kill Brave first so the profile isn't locked
    _close_brave_if_running()
    
    async def _fetch():
        pw = None
        context = None
        try:
            from playwright.async_api import async_playwright
            _log("Starting Playwright...")
            pw = await async_playwright().start()
            
            # A Chromium profile IS its own user-data directory; only Brave
            # keeps profiles inside one shared tree and selects one by name.
            user_data_dir, profile_dir_name = FacebookAutomation._profile_layout(
                brave_profile_path)

            _log(f"Launching browser: dir={user_data_dir}, profile={profile_dir_name}")
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=browser_choice.executable_path(),
                headless=True,
                viewport=SMALL_VIEWPORT,
                args=[*([f"--profile-directory={profile_dir_name}"] if profile_dir_name else []),
                      *MEMORY_FLAGS],
            )
            
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Enable console logging for debugging
            page.on("console", lambda msg: _log(f"Browser console: {msg.text}"))
            
            _log("Navigating to facebook.com/me...")
            await page.goto("https://www.facebook.com/me", timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(5)  # Increased wait time for page to fully load
            
            url = page.url
            _log(f"Current URL: {url}")
            
            if "login" in url or "checkpoint" in url:
                _log("Not logged in (redirected to login/checkpoint)")
                return None
            
            # Take a screenshot for debugging (optional)
            try:
                await page.screenshot(path="debug_profile_page.png")
                _log("Screenshot saved to debug_profile_page.png")
            except Exception:
                pass
            
            # Get page HTML for debugging
            try:
                html_content = await page.content()
                _log(f"Page HTML length: {len(html_content)} chars")
                # Check if og:title is in the HTML
                if 'property="og:title"' in html_content:
                    _log("✓ og:title meta tag found in HTML")
                else:
                    _log("✗ og:title meta tag NOT found in HTML")
            except Exception as e:
                _log(f"Could not get page HTML: {e}")
            
            name = await page.evaluate('''() => {
                function isValidName(text) {
                    if (!text || text.length < 2 || text.length > 100) return false;
                    const lower = text.toLowerCase();
                    const invalid = ['facebook', 'home', 'watch', 'marketplace', 'groups',
                                    'gaming', 'menu', 'notifications', 'messages',
                                    'settings', 'log out', 'create', 'edit', 'add', 'photo',
                                    'search', 'friend', 'posts', 'about', 'photos', 'videos',
                                    'more', 'see all', 'see more', 'intro', 'details'];
                    if (invalid.some(inv => lower === inv || lower.includes(inv))) return false;
                    // Allow all-lowercase if it's short (could be a valid name)
                    if (text === text.toLowerCase() && text.length > 15) return false;
                    if (text.endsWith('...') || text.endsWith('…')) return false;
                    return true;
                }
                
                // Strategy 1: og:title meta tag
                const ogTitle = document.querySelector('meta[property="og:title"]');
                if (ogTitle && ogTitle.content) {
                    const name = ogTitle.content.trim();
                    console.log('Found og:title:', name);
                    if (isValidName(name)) return name;
                }
                
                // Strategy 2: title tag (fallback)
                const titleTag = document.querySelector('title');
                if (titleTag && titleTag.textContent) {
                    const name = titleTag.textContent.trim();
                    console.log('Found title:', name);
                    if (isValidName(name) && !name.includes('Facebook')) {
                        return name;
                    }
                }
                
                // Strategy 3: Look for h1 elements
                const h1Elements = document.querySelectorAll('h1');
                for (const h1 of h1Elements) {
                    const text = (h1.innerText || h1.textContent || '').trim();
                    console.log('Found h1:', text);
                    if (isValidName(text)) return text;
                }
                
                // Strategy 4: Look for profile name in specific areas (more aggressive)
                const profileSelectors = [
                    '[role="main"] h1',
                    '[data-pagelet="ProfileTimeline"] h1',
                    '[data-pagelet="ProfileActions"] + * h1',
                    'div[dir="auto"] span[dir="auto"]',
                ];
                
                for (const selector of profileSelectors) {
                    try {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            const text = (el.innerText || el.textContent || '').trim();
                            console.log('Found with selector', selector, ':', text);
                            if (text && text.length > 2 && text.length < 100 && isValidName(text)) {
                                return text;
                            }
                        }
                    } catch (e) {
                        console.log('Selector error:', e);
                    }
                }
                
                // Strategy 5: Look for any large text near the top (could be the name)
                const allSpans = document.querySelectorAll('span, div');
                for (const el of allSpans) {
                    const rect = el.getBoundingClientRect();
                    // Look for large text in the top portion of the page
                    if (rect.top < 500 && rect.width > 100) {
                        const text = (el.innerText || el.textContent || '').trim();
                        if (text && text.length > 3 && text.length < 50 && isValidName(text)) {
                            // Check if this element is visible and prominent
                            const style = window.getComputedStyle(el);
                            const fontSize = parseInt(style.fontSize);
                            if (fontSize > 16) {  // Larger font = likely the name
                                console.log('Found large text:', text, 'fontSize:', fontSize);
                                return text;
                            }
                        }
                    }
                }
                
                return null;
            }''')
            
            _log(f"Extracted name: {name}")
            return name
        except Exception as e:
            _log(f"ERROR: {e}")
            return None
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass
    
    try:
        result = _asyncio.run(_fetch())
        _log(f"Final result: {result}")
        return result
    except Exception as e:
        _log(f"FATAL: {e}")
        return None

SMALL_VIEWPORT = {"width": 1024, "height": 768}
TINY_VIEWPORT = {"width": 640, "height": 480}
MICRO_VIEWPORT = {"width": 480, "height": 360}

# One owner for "is a Facebook login gate on this page".
#
# Three things mean the account cannot use the page, and each catches what the
# others miss:
#   1. the 'See more on Facebook' overlay, which covers a post without ever
#      changing the URL;
#   2. a visible email / password field, i.e. a plain login form;
#   3. the "Continue as <name> / Use another profile" account chooser. When
#      Facebook invalidates a session server-side the profile KEEPS its cookies
#      (c_user and xs included) and lands here at facebook.com/ with no password
#      field at all - so a test that only looks for a login form calls it logged
#      in, and the app counts a dead account as active.
LOGIN_GATE_JS = """() => {
    const vis = e => { const r = e.getBoundingClientRect();
                       return r.width > 0 && r.height > 0; };
    for (const d of document.querySelectorAll('[role="dialog"]')) {
        if (!vis(d)) continue;
        if ((d.innerText || '').toLowerCase().includes('see more on facebook')) return true;
    }
    for (const i of document.querySelectorAll('input')) {
        if (!vis(i)) continue;
        const name = (i.name || '').toLowerCase();
        const type = (i.type || '').toLowerCase();
        if (name === 'email' || name === 'pass' ||
            type === 'email' || type === 'password') return true;
    }
    const body = (document.body ? document.body.innerText : '').toLowerCase();
    if (body.includes('use another profile')) return true;
    if (body.includes('log into another account')) return true;
    return false;
}"""


MEMORY_FLAGS = [
    "--disable-gpu",
    "--disable-gpu-compositing",
    "--disable-gpu-rasterization",
    "--disable-gpu-sandbox",
    "--disable-software-rasterizer",
    "--disable-dev-shm-usage",
    "--no-sandbox",  # Disable sandbox for concurrent launches
    "--disable-setuid-sandbox",
    "--no-first-run",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--metrics-recording-only",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-ipc-flooding-protection",
    # Moderate memory limiting for stable operation
    "--renderer-process-limit=1",  # Limit renderer processes instead of single-process
    "--js-flags=--max-old-space-size=256",
    # Disable features that consume RAM
    "--disable-component-extensions-with-background-pages",
    "--disable-features=Translate,ChromeWhatsNewUI,InterestFeedContentSuggestions",
]

# Watching decodes one live video per profile, all at the same time, and two
# MEMORY_FLAGS entries make that impossible:
#   --renderer-process-limit=1        puts every watch page in ONE renderer
#   --js-flags=--max-old-space-size=256   caps that single renderer's JS heap
# Measured on a 9-profile live watch with those flags on: every page starts
# playing, then 3-4 freeze within 30s at readyState 2 with currentTime stuck
# and paused still false - i.e. they LOOK healthy and watch nothing. Dropping
# the two caps gives each context its own renderer and its own heap.
WATCH_FLAGS = [f for f in MEMORY_FLAGS
               if not f.startswith(("--renderer-process-limit=", "--js-flags="))]

# Lighter memory flags for dual-browser mode (less aggressive)
# Interactive login needs a permissive browser, not a memory-tuned one.
# MEMORY_FLAGS breaks the 2FA step two ways: --renderer-process-limit=1
# starves the cross-origin google.com reCAPTCHA iframe of a renderer, and
# --disable-background-networking plus the 256MB JS heap cap leave the widget
# reporting "Cannot contact reCAPTCHA". One human-driven browser makes the RAM
# savings irrelevant, so keep only the flags that aid stability.
LOGIN_FLAGS = [
    # Chromium otherwise ships a "Blink automation" fingerprint that scores
    # the session as a bot before a single key is pressed, which is what puts
    # an "I am not a robot" box on the login form.
    "--disable-blink-features=AutomationControlled",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--disable-extensions",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
]


# Facebook appends its own tracking to any link it resolves: rdid on a
# redirect, mibextid/__cft__/__tn__ on feed links. None of it identifies the
# post, and leaving it in made identity checks compare noise.
_TRACKING_PARAMS = ("rdid", "share_url", "mibextid", "__cft__", "__tn__",
                    "notif_id", "notif_t", "ref", "refid")


def _without_tracking(url: str) -> str:
    """The same URL with Facebook's tracking parameters removed."""
    try:
        parts = urllib.parse.urlsplit(url or "")
        kept = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                if k.split("[")[0] not in _TRACKING_PARAMS]
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path,
             urllib.parse.urlencode(kept), parts.fragment))
    except Exception:
        return url or ""


class FacebookAutomation:
    # Seconds an unattended login lets a gate URL clear itself before
    # calling it a checkpoint. Long enough for the device-based login
    # redirect, far short of the 120 s a watching human gets.
    UNATTENDED_GATE_GRACE_S = 20
    # Seconds a visible login waits for the operator to answer a reCAPTCHA
    # picture challenge. Only a person can answer one, so a headless run
    # skips the wait entirely.
    CAPTCHA_WAIT_S = 180


    LOGIN_URL = "https://www.facebook.com/"

    def __init__(self, log_callback: Callable[[str], None] = print, debug: bool = False):
        self.log = log_callback
        self.debug = debug
        self._pw = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._browser = None  # browser instance for concurrent mode
        self._post_url_before_share: str | None = None  # URL before sharing, for verifying redirects
        self._tile: tuple[int, int] | None = None  # this window's grid cell, if tiled

    # ── Concurrent profile support ─────────────────────────

    async def extract_storage_state(self, brave_path: str, return_logged_in: bool = False,
                                    skip_navigation: bool = False):
        """Extract cookies/storage from a Brave profile and return storage_state.

        Opens a temporary headless persistent context for the profile,
        navigates to Facebook, captures the full storage state
        (cookies + localStorage + sessionStorage), then closes.

        Tries first WITHOUT killing Brave — if Brave is running and the
        profile is locked, it kills Brave and retries once.
        Returns None if extraction fails.

        If return_logged_in=True, returns (state, logged_in) instead of state;
        logged_in is True only when the profile lands on the Facebook HOME
        page with no login UI (see _is_home_url) and is False when extraction
        fails.  The plain state dict does
        NOT indicate login status — only the DOM check does.

        If skip_navigation=True, the facebook.com navigation, settle sleep and
        login-UI poll are skipped entirely: the cookies live in the persistent
        context regardless of navigation, so the state can be captured
        directly (~4-6s instead of ~10-20s, and zero Facebook traffic).
        Login status is then unknown — callers on this path rely on the live
        _is_logged_in() check that runs before every action anyway. Not
        compatible with return_logged_in=True.

        RAM: blocks images/media during extraction to keep peak usage low.
        """
        self.log(f"Extracting login state from profile...")

        pw = await async_playwright().start()

        async def _do_extract(kill_brave: bool = False) -> dict | None:
            if kill_brave:
                _close_brave_if_running()
                await asyncio.sleep(1)

            user_data_dir, profile_dir_name = self._profile_layout(brave_path)

            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=browser_choice.executable_path(),
                headless=True,
                viewport=SMALL_VIEWPORT,
                args=[*([f"--profile-directory={profile_dir_name}"] if profile_dir_name else []),
                      *MEMORY_FLAGS],
            )
            pages = ctx.pages
            page = pages[0] if pages else await ctx.new_page()
            # Block resources during extraction to keep RAM low
            try:
                await page.route("**/*", lambda route: route.abort()
                    if route.request.resource_type in ["image", "media", "font"]
                    else route.continue_())
            except Exception:
                pass

            if skip_navigation:
                # Cookies live in the persistent context regardless of any
                # navigation — capture them directly with zero FB traffic.
                self.last_account_status = "unknown"
                state = await ctx.storage_state()
                await ctx.close()
                self.log("Storage state extracted (fast path, no navigation)")
                return state, False

            # Navigate to Facebook with retries. A page-load timeout/network blip
            # is NOT fatal: the profile's cookies/storage live in the persistent
            # context regardless, so we can still extract a valid storage_state.
            # We only need the response (cookies), NOT the rendered DOM, so wait
            # for "commit". Stalled connections usually clear on a FRESH TCP
            # connection, so use a short timeout + several quick attempts.
            for attempt in range(5):
                try:
                    await page.goto("https://www.facebook.com/",
                                    timeout=8000, wait_until="commit")
                    break
                except Exception as e:
                    if attempt < 4:
                        self.log(f"  ⚠️  Connection attempt {attempt + 1}/5 stalled ({str(e).split(chr(10))[0]}), retrying...")
                        await asyncio.sleep(1)
                    else:
                        self.log(f"  ⚠️  Facebook unreachable — continuing with stored cookies")
            await asyncio.sleep(2)

            # Wait up to 10s to land on the Facebook HOME page. Logged in
            # means the account can use its home page: a session Facebook
            # gates (checkpoint, confirmemail.php, two-factor, login) is sent
            # away from "/" and does not count. The URL alone can still lie —
            # a 'See more on Facebook' overlay can appear while the URL stays
            # on "/" — so ALSO check the DOM for visible login fields before
            # declaring logged_in=True.
            logged_in = False
            for _ in range(10):
                try:
                    url = page.url.lower()
                    if self._is_home_url(url):
                        has_login_ui = await page.evaluate(LOGIN_GATE_JS)
                        if not has_login_ui:
                            logged_in = True
                            break
                except Exception:
                    pass
                await asyncio.sleep(0.5)

            if not logged_in:
                status = await self._classify_account_access(page)
                self.last_account_status = status
                self.log(f"Profile access status: {status}")
            else:
                self.last_account_status = "logged_in"

            state = await ctx.storage_state()
            await ctx.close()
            self.log(f"Storage state extracted (logged_in={logged_in})")
            return state, logged_in

        # Try without killing Brave first
        try:
            state, logged_in = await _do_extract(kill_brave=False)
        except Exception as e:
            err_str = str(e).lower()
            if any(kw in err_str for kw in ["locked", "in use", "another instance", "profile"]):
                self.log(f"Profile locked, killing Brave and retrying... ({e})")
                try:
                    state, logged_in = await _do_extract(kill_brave=True)
                except Exception as e2:
                    self.log(f"Failed to extract storage state after retry: {e2}")
                    return (None, False) if return_logged_in else None
            else:
                self.log(f"Failed to extract storage state: {e}")
                return (None, False) if return_logged_in else None
        finally:
            await pw.stop()

        if return_logged_in:
            return state, logged_in
        return state

    # The composer's Post button, in every language Facebook serves it.
    # One owner: the group/composer flow and the share-composer retry
    # both press this button.
    COMPOSER_POST_SELECTORS = [
    # English
    '[role="dialog"] [aria-label="Post"]',
    '[role="dialog"] div[role="button"]:has-text-is("Post")',
    '[role="dialog"] div[role="button"]:text-is("Post")',
    # Filipino/Tagalog
    '[role="dialog"] div[role="button"]:has-text-is("I-post")',
    '[role="dialog"] div[role="button"]:text-is("I-post")',
    '[role="dialog"] div[role="button"]:has-text-is("Mag-post")',
    '[role="dialog"] div[role="button"]:text-is("Mag-post")',
    # Spanish
    '[role="dialog"] div[role="button"]:has-text-is("Publicar")',
    '[role="dialog"] div[role="button"]:text-is("Publicar")',
    # French
    '[role="dialog"] div[role="button"]:has-text-is("Publier")',
    '[role="dialog"] div[role="button"]:text-is("Publier")',
    # Portuguese
    '[role="dialog"] div[role="button"]:has-text-is("Postar")',
    '[role="dialog"] div[role="button"]:text-is("Postar")',
    # German
    '[role="dialog"] div[role="button"]:has-text-is("Posten")',
    '[role="dialog"] div[role="button"]:text-is("Posten")',
    # Italian
    '[role="dialog"] div[role="button"]:has-text-is("Pubblica")',
    '[role="dialog"] div[role="button"]:text-is("Pubblica")',
    ]

    async def init_from_storage(self, browser, storage_state: dict,
                                viewport: dict | None = None,
                                block_resources: bool = True,
                                no_viewport: bool = False):
        """Initialize automation with a context in a given browser using saved storage state.

        Creates an isolated incognito context with the profile's cookies
        and a small viewport, then sets it as the current context/page.
        Stores the browser reference so it can be closed later.
        Enables resource blocking to cut RAM usage by ~50-70%.

        Pass block_resources=False for a page that streams video. It skips
        page.route() entirely rather than registering a pass-through handler:
        an installed route sends EVERY request - including each media segment
        of a live stream, for every open page - through this Python process,
        which is exactly the traffic a watch cannot afford to queue behind.
        """
        # no_viewport ties the page size to the real window, which is what a
        # tiled watch needs: a fixed 1024x768 viewport inside a window resized
        # to a grid cell would render at the wrong size and get cropped.
        vp = viewport or SMALL_VIEWPORT
        self.context = await browser.new_context(
            storage_state=storage_state,
            viewport=None if no_viewport else vp,
            no_viewport=no_viewport,
        )
        self.page = await self.context.new_page()
        if block_resources:
            await self._enable_resource_blocking(self.page)
        else:
            self._block_resources = False
        self._pw = None
        self._browser = browser

    async def close_context(self):
        """Close this automation's context/page only (not the browser).

        Navigates to about:blank before closing to trigger V8 garbage
        collection and release DOM memory immediately.
        """
        if self.page:
            try:
                # Navigate to about:blank first to trigger GC and release DOM
                await self.page.goto("about:blank", timeout=5000, wait_until="domcontentloaded")
            except Exception:
                pass
            try:
                await self.page.close()
            except Exception:
                pass
            self.page = None
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None

    # ── Driver lifecycle ───────────────────────────────────

    @staticmethod
    def _profile_layout(profile_path: str) -> tuple[str, str | None]:
        """(user_data_dir, profile_directory) for opening one account.

        Brave keeps every profile inside one shared "User Data" tree and
        selects one with --profile-directory. A Chromium profile IS its own
        user-data directory, and its data lives in the "Default" folder the
        browser creates inside it - so passing Brave's split for Chromium
        opens the PARENT of the profile and finds no cookies at all. That is
        what made every comment report "logged out or session expired" for
        accounts that had just logged in.
        """
        if browser_choice.current_browser() == browser_choice.CHROMIUM:
            return profile_path, None
        return os.path.dirname(profile_path), os.path.basename(profile_path)

    async def start_browser(self, profile_path: str, headless: bool = True,
                            flags: list | None = None,
                            tile: tuple[int, int] | None = None):
        """Launch the browser with the given Brave profile directory.

        headless defaults to True, which is what every existing caller relies
        on. Pass headless=False when a human has to interact with the page,
        e.g. clearing a Facebook login checkpoint.

        flags defaults to MEMORY_FLAGS. Pass LOGIN_FLAGS for interactive
        login, where reCAPTCHA has to work and RAM tuning does not matter.

        tile is (slot, count): this window's cell in a grid of `count`
        windows, so a wave of logins tiles the screen instead of stacking on
        one spot. See _tile_window for why it is not a --window-size flag.
        
        The profile_path should point to a specific Brave profile directory
        (e.g., C:/Users/.../Brave-Browser/User Data/Default).
        
        Playwright's launch_persistent_context expects user_data_dir to be
        the parent "User Data" directory and uses --profile-directory to
        select the specific profile. We split the path accordingly to
        ensure existing cookies and sessions are preserved.
        """
        self.log("Starting browser...")

        # Brave shares one User Data tree, so a running Brave locks the
        # profile. A Chromium profile is private to this launch; killing the
        # user's other browsers would be gratuitous.
        if browser_choice.current_browser() != browser_choice.CHROMIUM:
            _close_brave_if_running()
            await asyncio.sleep(1)

        self._pw = await async_playwright().start()

        # Split profile path into User Data directory and profile directory name
        # e.g. "C:/.../Brave-Browser/User Data/Default" → parent="C:/.../User Data", name="Default"
        # Brave selects a profile inside one shared "User Data" tree; a
        # Chromium profile IS its own user-data directory. Passing Brave's
        # split to Chromium would open the parent folder and lose the session.
        user_data_dir, profile_dir_name = self._profile_layout(profile_path)

        self.log(f"Using profile directory: {profile_dir_name}")
        self.log(f"User Data dir: {user_data_dir}")

        launch = {"viewport": SMALL_VIEWPORT}
        if tile:
            # The page has to follow the small tiled window, not sit inside it
            # at a fixed 1024x768.
            launch = {"no_viewport": True}

        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=browser_choice.executable_path(),
            headless=headless,  # background by default; False shows a window
            args=[
                *([f"--profile-directory={profile_dir_name}"] if profile_dir_name else []),
                # Shrinking the browser's own unit is what makes a tile
                # possible at all; see _tile_window.
                *([f"--force-device-scale-factor={browser_choice.GRID_SCALE:g}"]
                  if tile else ["--window-position=50,50"]),
                *(MEMORY_FLAGS if flags is None else flags),
            ],
            **launch,
        )
        
        self.log("Browser started in background mode" if headless
                 else "Browser started in a visible window")

        # Use first restored tab as main page, close extras
        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()
        await self._enable_resource_blocking(self.page)
        for p in pages[1:]:
            try:
                await p.close()
            except Exception:
                pass
        try:
            # Chromium sets navigator.webdriver=true whatever the flags say,
            # and it is the first thing a bot check reads.
            # false, not undefined: an ordinary Chrome reports false, and a
            # missing property is its own anomaly.
            await self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => false});")
        except Exception:
            pass

        self._tile = tile
        if tile:
            await self._tile_window(tile[0], tile[1])
        self.log("Browser started")

    async def _tile_window(self, slot: int, count: int) -> None:
        """Move this window into its own cell of a grid of `count`.

        Not --window-size: Chromium refuses a window under about 515 of its
        own units wide, which is wider than one cell of a 5x5 grid, so the
        flag comes back clamped and the windows overlap. Launching with
        --force-device-scale-factor makes those units smaller than a screen
        pixel, and this places the window inside that larger coordinate
        space, which the page itself reports as screen.availWidth.

        A window that will not move is cosmetic: log it and log in anyway.
        """
        try:
            space = await self.page.evaluate(
                "() => [screen.availWidth, screen.availHeight]")
            x, y, w, h = browser_choice.grid_slot(slot, count,
                                                  int(space[0]), int(space[1]))
            cdp = await self.context.new_cdp_session(self.page)
            window_id = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
            await cdp.send("Browser.setWindowBounds",
                           {"windowId": window_id,
                            "bounds": {"left": x, "top": y, "width": w, "height": h}})
        except Exception as e:  # noqa: BLE001 - a misplaced window never fails a login
            self.log(f"Could not tile the window: {type(e).__name__}: {e}")

    async def _set_window_bounds(self, bounds: dict) -> None:
        """Move/resize this window through CDP. Bounds are in the browser's
        own units, the same space _tile_window lays the grid out in."""
        cdp = await self.context.new_cdp_session(self.page)
        window_id = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
        await cdp.send("Browser.setWindowBounds",
                       {"windowId": window_id, "bounds": bounds})

    # Facebook does not only use Google reCAPTCHA. Its own challenge is an
    # Arkose Labs / FunCaptcha widget ("confirm you are human", a rotating
    # picture puzzle), which is a different host and has no checkbox at all -
    # so it was never detected and every one of them was recorded as a
    # checkpoint or as an unexplained failure.
    ARKOSE_HOSTS = ("arkoselabs.com", "funcaptcha.co", "arkoselabs.cn")
    CAPTCHA_TEXTS = ("confirm you're human", "confirm that you're human",
                     "confirm you are human", "security check",
                     "enter the characters", "solve this puzzle",
                     "let's confirm you're human", "i'm not a robot")

    async def _frame_urls(self) -> list[str]:
        try:
            return [(getattr(f, "url", "") or "") for f in self.page.frames]
        except Exception:
            return []

    async def _captcha_frame(self):
        """The "I'm not a robot" checkbox frame on this page, or None.

        reCAPTCHA runs in two google.com iframes: the anchor frame holds the
        checkbox, the bframe holds the picture challenge. Only the anchor can
        be clicked.
        """
        try:
            frames = self.page.frames
        except Exception:
            return None
        for frame in frames:
            url = (getattr(frame, "url", "") or "")
            if "recaptcha" in url and "anchor" in url:
                return frame
        return None

    async def _arkose_present(self) -> bool:
        """Whether Facebook's own picture challenge is on the page.

        There is nothing to click here: an Arkose puzzle is answered by a
        person or not at all.
        """
        if any(any(h in url for h in self.ARKOSE_HOSTS)
               for url in await self._frame_urls()):
            return True
        try:
            body = (await self.page.locator("body").inner_text(timeout=3000)).lower()
        except Exception:
            return False
        return any(t in body for t in self.CAPTCHA_TEXTS)

    async def _captcha_challenge_open(self) -> bool:
        """Whether the picture challenge is up - the part no click can pass."""
        try:
            frames = self.page.frames
        except Exception:
            return False
        return any("recaptcha" in (getattr(f, "url", "") or "")
                   and "bframe" in (getattr(f, "url", "") or "") for f in frames)

    async def _captcha_token(self) -> bool:
        """Whether reCAPTCHA has issued a token, which is what "solved" means."""
        try:
            filled = await self.page.evaluate(
                "() => { const el = document.querySelector("
                "'#g-recaptcha-response, textarea[name=\"g-recaptcha-response\"]');"
                " return el ? el.value.length : 0; }")
        except Exception:
            return False
        return bool(filled)

    async def handle_recaptcha(self, wait_s: float | None = None) -> str:
        """Deal with an "I'm not a robot" box. Returns "none", "solved" or
        "needs human".

        The checkbox itself is clicked here: on a profile with history
        reCAPTCHA usually issues its token from that click alone. A picture
        challenge is a different thing - it is meant to be answered by a
        person, and this does not answer it. Instead the window is enlarged
        and raised so the operator can, then put back in its tile.

        Headless there is nobody to ask, so the wait is skipped and the run
        records the verdict instead of hanging.
        """
        frame = await self._captcha_frame()
        if frame is None:
            # Facebook's own challenge, which has no checkbox to tick.
            if await self._arkose_present():
                self.log("Facebook picture challenge shown (Arkose)")
                if wait_s is None:
                    wait_s = self.CAPTCHA_WAIT_S if self._tile is not None else 0
                if wait_s <= 0:
                    return "needs human"
                self.log(f"Solve the challenge in this window ({int(wait_s)}s)")
                await self._focus_for_human()
                try:
                    for _ in range(int(wait_s)):
                        await asyncio.sleep(1)
                        if not await self._arkose_present():
                            return "solved"
                    return "needs human"
                finally:
                    await self._back_to_tile()
            return "none"
        if await self._captcha_token():
            return "solved"

        self.log("reCAPTCHA shown - ticking \"I'm not a robot\"...")
        try:
            box = frame.locator("#recaptcha-anchor")
            await box.click(timeout=10000)
        except Exception as e:  # noqa: BLE001 - the token check below decides
            self.log(f"  could not click the checkbox: {type(e).__name__}: {e}")

        # A checkbox-only reCAPTCHA issues its token within a second or two.
        for _ in range(10):
            await asyncio.sleep(1)
            if await self._captcha_token():
                self.log("reCAPTCHA passed")
                return "solved"
            if await self._captcha_challenge_open():
                break

        if wait_s is None:
            wait_s = self.CAPTCHA_WAIT_S if self._tile is not None else 0
        if wait_s <= 0:
            self.log("reCAPTCHA needs a picture challenge and no window is visible")
            return "needs human"

        self.log(f"reCAPTCHA picture challenge - solve it in this window "
                 f"({int(wait_s)}s)")
        await self._focus_for_human()
        try:
            for _ in range(int(wait_s)):
                await asyncio.sleep(1)
                if await self._captcha_token():
                    self.log("reCAPTCHA solved")
                    return "solved"
            return "needs human"
        finally:
            await self._back_to_tile()

    async def _focus_for_human(self) -> None:
        """Make this window big and frontmost: a grid cell is far too small to
        pick traffic lights in."""
        try:
            space = await self.page.evaluate(
                "() => [screen.availWidth, screen.availHeight]")
            width = int(int(space[0]) * 0.6)
            height = int(int(space[1]) * 0.8)
            await self._set_window_bounds({
                "left": (int(space[0]) - width) // 2,
                "top": (int(space[1]) - height) // 2,
                "width": width, "height": height, "windowState": "normal"})
            await self.page.bring_to_front()
        except Exception as e:  # noqa: BLE001 - cosmetic; the wait still runs
            self.log(f"Could not raise the window: {type(e).__name__}: {e}")

    async def _back_to_tile(self) -> None:
        """Return the window to its cell so the rest of the wave stays visible."""
        if self._tile is None:
            return
        await self._tile_window(self._tile[0], self._tile[1])

    async def start_browser_headless(self, profile_path: str, kill_existing: bool = True, viewport: dict = None):
        """Launch the browser in HEADLESS mode (background) with the given Brave profile directory.
        
        Perfect for automated friend requests - runs in the background without showing windows.

        Args:
            profile_path: Path to the Brave profile directory.
            kill_existing: If True, kills any running Brave processes first (NOT safe for concurrent).
            viewport: Viewport dict, e.g. MICRO_VIEWPORT. Defaults to SMALL_VIEWPORT.
        """
        self.log("Starting browser (headless mode)...")

        if kill_existing:
            _close_brave_if_running()
            await asyncio.sleep(1)
        
        # Check if profile is locked (for concurrent mode)
        if not kill_existing and _is_profile_locked(profile_path):
            self.log(f"⚠️  Profile appears locked, waiting up to 10s for unlock...")
            if not _wait_for_profile_unlock(profile_path, max_wait=10):
                self.log(f"❌ Profile still locked after 10s - attempting launch anyway...")
                # Don't raise error, let Playwright try and report the actual error

        self._pw = await async_playwright().start()

        user_data_dir, profile_dir_name = self._profile_layout(profile_path)

        self.log(f"Using profile: {profile_dir_name or user_data_dir} (background)")

        try:
            self.context = await self._pw.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=browser_choice.executable_path(),
                headless=True,  # HEADLESS MODE!
                viewport=viewport or SMALL_VIEWPORT,
                args=[
                    *([f"--profile-directory={profile_dir_name}"] if profile_dir_name else []),
                    *MEMORY_FLAGS,
                ],
            )
        except Exception as e:
            err_str = str(e).lower()
            if any(kw in err_str for kw in ["locked", "in use", "another instance"]):
                self.log(f"❌ Profile locked error: {e}")
                self.log(f"💡 Try closing Brave browser completely before running auto-setup")
                raise RuntimeError(f"Profile is locked by another Brave instance. Close Brave and try again.") from e
            raise

        # Use first tab
        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()
        await self._enable_resource_blocking(self.page)
        for p in pages[1:]:
            try:
                await p.close()
            except Exception:
                pass
        self.log("Browser started (headless)")

    async def go_to_facebook(self):
        """Navigate to Facebook with retry and recovery from about:blank."""
        for attempt in range(3):
            try:
                await self.page.goto(self.LOGIN_URL, timeout=60000,  # Increased to 60s
                                     wait_until="domcontentloaded")
                await asyncio.sleep(2)

                # Verify we actually landed on facebook.com, not about:blank
                current_url = (await self.page.evaluate("window.location.href") or "").lower()
                if "facebook.com" not in current_url:
                    self.log(f"Navigation landed on '{current_url}', retrying...")
                    await asyncio.sleep(1)
                    continue

                # Wait a bit more for the page to stabilize
                await asyncio.sleep(2)
                return
            except Exception as e:
                if attempt == 2:
                    self.log(f"Failed to reach Facebook after 3 attempts: {e}")
                    return
                self.log(f"Facebook navigation failed (attempt {attempt+1}), retrying: {e}")
                await asyncio.sleep(3)  # Increased retry delay

    # ── Profile Setup & Friend Management ────────────────────

    async def check_friends_count(self) -> int:
        """Navigate to own profile and determine how many friends this account has.

        Visits the profile's friends page and extracts the numeric friend count
        from the page text (e.g. "523 friends"). Returns 0 if unable to determine.
        """
        self.log("Checking friends count...")
        try:
            await self.page.goto("https://www.facebook.com/me/friends",
                                 timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            count = await self.page.evaluate(r'''() => {
                const text = document.body.innerText;
                const match = text.match(/([\d,]+)\s*friends?/i);
                if (match) return parseInt(match[1].replace(/,/g, ''));
                return 0;
            }''')
            self.log(f"Friends count: {count}")
            return count
        except Exception as e:
            self.log(f"Could not check friends count: {e}")
            return 0

    async def check_profile_setup(self) -> dict:
        """Check whether the Facebook profile has a picture, cover, and bio.

        Returns a dict:
          {
            "has_profile_pic": bool,
            "has_cover_photo": bool,
            "has_bio": bool,
            "bio_text": str or "",
          }
        """
        self.log("Checking profile setup...")
        result = {"has_profile_pic": False, "has_cover_photo": False,
                  "has_bio": False, "bio_text": ""}
        try:
            await self.page.goto("https://www.facebook.com/me",
                                 timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            info = await self.page.evaluate('''() => {
                const text = document.body.innerText;
                
                // Check for "Add profile picture" / "Add photo" buttons
                const allElements = [
                    ...document.querySelectorAll('[role="button"]'),
                    ...document.querySelectorAll('div, span, a'),
                ];
                
                let hasAddPhotoButton = false;
                for (const el of allElements) {
                    if (el.offsetParent === null) continue;
                    const btnText = (el.innerText || '').toLowerCase();
                    const btnLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                    
                    if (btnText.includes('add profile picture') || 
                        btnText.includes('add photo') ||
                        btnLabel.includes('add profile picture') ||
                        btnLabel.includes('add photo')) {
                        hasAddPhotoButton = true;
                        break;
                    }
                }
                
                // If "Add photo" button found → definitely NO picture
                // If NO "Add photo" button → profile HAS a picture (default assumption)
                let hasPic = !hasAddPhotoButton;
                
                // Secondary check: also look for any large image that could be a profile pic
                if (!hasAddPhotoButton) {
                    const avatars = [
                        ...document.querySelectorAll('img[src*="fbcdn"]'),
                        ...document.querySelectorAll('img[src*="scontent"]'),
                        ...document.querySelectorAll('img[src*="profile"]'),
                        ...document.querySelectorAll('img[alt*="profile" i]'),
                        ...document.querySelectorAll('image[href*="avatars"]'),
                        ...document.querySelectorAll('[data-pagelet="ProfileActions"] img'),
                    ];
                    
                    const hasLargeAvatar = avatars.some(el => {
                        if (el.offsetParent === null) return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 50;
                    });
                    
                    // If we find a large avatar, definitely has picture
                    // If we DON'T find one, STILL assume hasPic (no Add button = has picture)
                    hasPic = hasPic || hasLargeAvatar;
                }
                
                // Check for cover photo
                const covers = [
                    ...document.querySelectorAll('[data-pagelet="CoverPhoto"] img'),
                    ...document.querySelectorAll('img[alt*="cover" i]'),
                    ...document.querySelectorAll('img[src*="cover"]'),
                ];
                const hasCover = covers.some(el => {
                    if (el.offsetParent === null) return false;
                    const rect = el.getBoundingClientRect();
                    const src = el.getAttribute('src') || '';
                    const isDefault = src.includes('static') && src.includes('cover');
                    return rect.height > 50 && !isDefault;
                });
                
                return {
                    hasPic,
                    hasCover,
                    bioText: "",
                    hasAddPhotoButton
                };
            }''')
            result["has_profile_pic"] = info.get("hasPic", False)
            result["has_cover_photo"] = info.get("hasCover", False)
            result["bio_text"] = info.get("bioText", "")
            result["has_bio"] = bool(result["bio_text"])
            
            # Debug logging
            has_add_button = info.get("hasAddPhotoButton", False)
            if has_add_button:
                self.log(f"  🔍 Detected 'Add profile picture' button → No picture yet")
            
            self.log(f"Profile pic: {'✅' if result['has_profile_pic'] else '❌'}, "
                     f"Cover: {'✅' if result['has_cover_photo'] else '❌'}")
        except Exception as e:
            self.log(f"Could not check profile setup: {e}")
        return result

    async def auto_add_friends(self, target_count: int = 50, max_requests: int = 200) -> int:
        """Send friend requests to suggested people until target_count is reached.

        Navigates to Facebook's friend suggestions page, clicks "Add Friend"
        on visible suggestions, scrolls for more, and clicks "See More" buttons
        to load additional suggestions. Returns the number of friend requests
        actually sent.

        Args:
            target_count: Stop once this many requests have been sent.
            max_requests: Safety cap — never send more than this.
        """
        self.log(f"Auto-adding friends — target: {target_count}")
        sent = 0
        consecutive_empty = 0

        try:
            await self.page.goto("https://www.facebook.com/friends/suggestions/",
                                 timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            for _ in range(max_requests):
                if sent >= target_count:
                    break

                # Phase 1: Click all visible "Add Friend" buttons
                clicked = await self.page.evaluate('''() => {
                        // Collect all potential Add Friend buttons using standard selectors + JS text filtering
                        // (Playwright pseudo-classes like :has-text-is are invalid in querySelectorAll)
                        const candidates = [
                            ...document.querySelectorAll('div[aria-label="Add Friend"], span[aria-label="Add Friend"]'),
                            ...document.querySelectorAll('[role="button"], button'),
                        ];
                        const seen = new Set();
                        let count = 0;
                        for (const el of candidates) {
                            if (seen.has(el)) continue;
                            seen.add(el);
                            if (el.offsetParent === null) continue;
                            if (el.getAttribute("aria-disabled") === "true") continue;
                            const text = (el.innerText || "").trim();
                            const label = (el.getAttribute("aria-label") || "").trim();
                            if (text !== "Add Friend" && label !== "Add Friend") continue;
                            el.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true}));
                            count++;
                            if (count >= 8) break;
                        }
                        return count;
                    }''')

                if clicked > 0:
                    sent += clicked
                    self.log(f"  Sent {clicked} friend request(s) — total: {sent}")
                    consecutive_empty = 0
                    await asyncio.sleep(random.uniform(2, 4))
                    continue

                consecutive_empty += 1

                # Phase 2: Look for a "See More" button (Facebook often uses this
                # instead of infinite scroll for friend suggestions)
                if consecutive_empty <= 3:
                    see_more = await self._find(
                        css=[
                            'div[role="button"]:has-text("See More")',
                            'div[role="button"]:has-text("See more")',
                            'a:has-text("See More")',
                            '[aria-label*="See more" i]',
                        ],
                        timeout=3,
                        visible_only=True,
                    )
                    if see_more:
                        self.log("  Clicking 'See More' for additional suggestions...")
                        await see_more.click(force=True)
                        await asyncio.sleep(random.uniform(2, 3))
                        consecutive_empty = 0
                        continue

                # Phase 3: Scroll down to trigger infinite scroll
                if consecutive_empty >= 5:
                    # After 5 empty + no See More, try scrolling one more time
                    await self.page.evaluate("window.scrollBy(0, 1200)")
                    await asyncio.sleep(random.uniform(1.5, 2.5))

                # Phase 4: If consistently empty, we've exhausted suggestions
                if consecutive_empty >= 10:
                    self.log("No more friend suggestions available")
                    break

        except Exception as e:
            self.log(f"Error during auto-add friends: {e}")

        self.log(f"Friend requests sent: {sent}")
        return sent

    async def send_friend_request_to_profile(self, profile_url: str) -> str:
        """Send a friend request to a specific Facebook profile.

        Navigates to the target profile's URL and clicks the "Add Friend" button.
        Also tries to click "Confirm" if the other person already sent us a request.

        Args:
            profile_url: Facebook profile URL

        Returns:
            'sent' if request was sent, 'pending' if already pending,
            'accepted' if we confirmed their request instead,
            'already_friends' if already friends, 'not_found' or 'error' on failure.
        """
        self.log(f"  → Sending request to: {profile_url}")

        try:
            await self.page.goto(profile_url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(4)

            # Scroll to make sure profile action buttons are loaded
            await self.page.evaluate("window.scrollBy(0, 300)")
            await asyncio.sleep(1)

            status = await self._detect_profile_status()

            if status == 'confirm':
                # They already sent us a request — accept it right away
                clicked = await self._click_confirm_buttons(max_click=1)
                if clicked > 0:
                    self.log(f"    ✅ Confirmed their request instead! (they sent first)")
                    return "accepted"
                # fallback: button detection said confirm but click failed
                # continue to try Add Friend below

            if status == 'friends':
                self.log(f"    ⏭️  Already friends")
                return "already_friends"

            if status == 'cancel':
                self.log(f"    ⏭️  Request already pending from us")
                return "pending"

            if status == 'message_only':
                self.log(f"    ⏭️  Message only — likely already friends or restricted")
                return "already_friends"

            # Status is 'add_friend' or 'unknown' — try to send request

            # Strategy 1: Playwright locator
            try:
                add_friend_btn = self.page.get_by_role("button").filter(has_text="Add friend")
                if await add_friend_btn.count() > 0:
                    await add_friend_btn.first.click(timeout=3000)
                    await asyncio.sleep(random.uniform(2, 3))
                    self.log(f"    ✅ Friend request sent! (Playwright)")
                    return "sent"
            except Exception as e:
                self.log(f"    ⚠️  Playwright method failed: {e}")

            # Strategy 2: Robust JS scan
            result = await self.page.evaluate('''() => {
                const candidates = [
                    ...document.querySelectorAll('[role="button"]'),
                    ...document.querySelectorAll('button'),
                    ...document.querySelectorAll('div[tabindex="0"]'),
                    ...document.querySelectorAll('div[aria-label]'),
                ];
                const seen = new Set();

                for (const el of candidates) {
                    if (seen.has(el)) continue;
                    seen.add(el);

                    const text  = (el.innerText  || '').trim();
                    const label = (el.getAttribute('aria-label') || '').trim();
                    const low_t = text.toLowerCase();
                    const low_l = label.toLowerCase();
                    const rect  = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    if (el.getAttribute('aria-disabled') === 'true') continue;

                    /* Add Friend */
                    if (low_l.includes('add friend') || low_t.includes('add friend')) {
                        if (low_t.includes('following') || low_t.includes('message')) continue;
                        try {
                            el.scrollIntoView({block: 'center'});
                            el.click();
                            return {success: true, status: 'sent'};
                        } catch(e) {
                            try {
                                el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                                return {success: true, status: 'sent'};
                            } catch(_) {}
                        }
                    }
                }

                return {success: false, status: 'not_found'};
            }''')

            if isinstance(result, dict) and result.get('success'):
                await asyncio.sleep(random.uniform(2, 3))
                self.log(f"    ✅ Friend request sent! (JavaScript)")
                return "sent"

            self.log(f"    ❌ Add Friend button not found")
            return "not_found"

        except Exception as e:
            self.log(f"    ❌ Error: {e}")
            return "error"

    async def accept_requests_from_followers_page(self, my_profile_url: str, all_profile_urls: dict) -> int:
        """Accept friend requests by going to YOUR followers page, clicking each follower, then confirming.

        Goes to your profile's followers tab (&sk=followers), finds each follower's profile link,
        clicks it to visit their profile, then clicks the Confirm button there.

        Args:
            my_profile_url: YOUR Facebook profile URL
            all_profile_urls: Dict of all profile URLs to match against

        Returns:
            Number of requests accepted.
        """
        self.log(f"  📍 Visiting YOUR followers page...")
        accepted = 0
        
        try:
            # Add &sk=followers to go to YOUR followers tab
            followers_url = my_profile_url
            if '?' in my_profile_url:
                followers_url = my_profile_url + "&sk=followers"
            else:
                followers_url = my_profile_url + "?sk=followers"
            
            self.log(f"     URL: {followers_url}")
            
            # Navigate to YOUR followers page
            await self.page.goto(followers_url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # Scroll MULTIPLE times to ensure content loads
            self.log(f"     Scrolling to load followers...")
            for i in range(3):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await asyncio.sleep(2)
            
            # Additional wait for content to render
            await asyncio.sleep(2)

            # Get list of follower profile URLs from the page with AGGRESSIVE extraction
            follower_links = await self.page.evaluate('''(myProfileUrl) => {
                // AGGRESSIVE: Look for ALL profile links on page (multiple patterns)
                const allLinks = [
                    ...document.querySelectorAll('a[href*="facebook.com/profile.php?id="]'),
                    ...document.querySelectorAll('a[href*="facebook.com/"]'),
                    ...document.querySelectorAll('a[role="link"]'),
                ];
                
                const uniqueUrls = new Set();
                
                // Extract my profile ID from URL
                const myIdMatch = myProfileUrl.match(/id=(\\d+)/);
                const myId = myIdMatch ? myIdMatch[1] : null;
                
                console.log('My Profile ID:', myId);
                console.log('Total links found:', allLinks.length);
                
                // Track what we're seeing for debugging
                const debugInfo = {
                    totalLinks: allLinks.length,
                    profileLinks: 0,
                    myProfileLinks: 0,
                    otherProfileLinks: 0
                };
                
                allLinks.forEach(link => {
                    const href = link.href;
                    
                    // Try to extract profile URL using multiple patterns
                    let profileUrl = null;
                    let profileId = null;
                    
                    // Pattern 1: profile.php?id=123456
                    let match = href.match(/https:\\/\\/www\\.facebook\\.com\\/profile\\.php\\?id=(\\d+)/);
                    if (match) {
                        profileId = match[1];
                        profileUrl = `https://www.facebook.com/profile.php?id=${profileId}`;
                        debugInfo.profileLinks++;
                    }
                    
                    // Pattern 2: /username style (not supported for new accounts typically)
                    if (!profileUrl && href.includes('facebook.com/') && !href.includes('profile.php')) {
                        match = href.match(/https:\\/\\/www\\.facebook\\.com\\/([^/?&#]+)/);
                        if (match && match[1] !== 'me' && match[1] !== 'friends' && 
                            match[1] !== 'groups' && match[1] !== 'pages' && 
                            match[1] !== 'watch' && match[1] !== 'marketplace') {
                            // This might be a username, but we'll skip for now
                            // to focus on profile.php?id= format
                        }
                    }
                    
                    if (profileUrl && profileId) {
                        // Skip if this is MY profile
                        if (myId && profileId === myId) {
                            console.log('  -> Skipping own profile:', profileId);
                            debugInfo.myProfileLinks++;
                        } else {
                            console.log('  -> Adding follower:', profileId);
                            uniqueUrls.add(profileUrl);
                            debugInfo.otherProfileLinks++;
                        }
                    }
                });
                
                console.log('Debug info:', debugInfo);
                console.log('Final follower URLs:', Array.from(uniqueUrls));
                return {
                    urls: Array.from(uniqueUrls),
                    debug: debugInfo
                };
            }''', my_profile_url)
            
            # Extract the URLs array from result
            follower_links_data = follower_links or {}
            if isinstance(follower_links, list):
                # Backward compatibility if evaluate returns just array
                follower_links = follower_links
            else:
                # New format with debug info
                debug_info = follower_links_data.get('debug', {})
                self.log(f"     🔍 Link extraction debug:")
                self.log(f"        Total links found: {debug_info.get('totalLinks', 0)}")
                self.log(f"        Profile links: {debug_info.get('profileLinks', 0)}")
                self.log(f"        Own profile links: {debug_info.get('myProfileLinks', 0)}")
                self.log(f"        Other profile links: {debug_info.get('otherProfileLinks', 0)}")
                follower_links = follower_links_data.get('urls', [])            
            self.log(f"     Found {len(follower_links)} follower profile(s) (excluding self)")
            
            if len(follower_links) == 0:
                self.log(f"     ℹ️  No OTHER followers found on page")
                
                # Debug: Take screenshot of the page we're looking at
                try:
                    import tempfile
                    screenshot_path = os.path.join(tempfile.gettempdir(), f"followers_page_{int(time.time())}.png")
                    await self.page.screenshot(path=screenshot_path, full_page=True)
                    self.log(f"     📸 Full page screenshot: {screenshot_path}")
                except Exception as e:
                    self.log(f"     ⚠️  Screenshot failed: {e}")
                
                # Debug: show all profile links to see what's there
                all_links = await self.page.evaluate('''() => {
                    const links = [
                        ...document.querySelectorAll('a[href*="profile.php?id="]'),
                        ...document.querySelectorAll('a[href*="facebook.com/"]')
                    ];
                    return links.slice(0, 20).map(l => ({
                        href: l.href, 
                        text: l.innerText.substring(0, 30),
                        visible: l.offsetParent !== null
                    }));
                }''')
                
                if all_links:
                    self.log(f"     🔍 First {len(all_links)} links on page:")
                    for i, link in enumerate(all_links, 1):
                        visible_marker = "✅" if link.get('visible') else "❌"
                        self.log(f"         {i}. {visible_marker} {link.get('href', '')[:60]} - {link.get('text', '').strip()}")
                else:
                    self.log(f"     ⚠️  No links found at all on page!")
                    
                # Debug: Check page content for follower-related text
                page_info = await self.page.evaluate('''() => {
                    const bodyText = document.body.innerText;
                    return {
                        hasFollowers: bodyText.includes('Followers') || bodyText.includes('followers'),
                        hasNoContent: bodyText.includes('No content') || bodyText.includes('Nothing'),
                        url: window.location.href,
                        title: document.title
                    };
                }''')
                
                self.log(f"     🔍 Page info:")
                self.log(f"         URL: {page_info.get('url', '')}")
                self.log(f"         Title: {page_info.get('title', '')}")
                self.log(f"         Has 'Followers' text: {page_info.get('hasFollowers', False)}")
                self.log(f"         Has 'No content' text: {page_info.get('hasNoContent', False)}")
                self.log(f"     🔍 Your profile: {my_profile_url}")
                
                return 0
            
            # Visit each follower's profile and look for Confirm button
            for idx, follower_url in enumerate(follower_links, 1):
                # Check if this is one of our known profiles
                matched_name = None
                for name, profile_url in all_profile_urls.items():
                    if profile_url in follower_url or follower_url in profile_url:
                        matched_name = name
                        break
                
                profile_display = matched_name if matched_name else follower_url[-30:]
                self.log(f"\n     [{idx}/{len(follower_links)}] Checking: {profile_display}")
                self.log(f"          Going to: {follower_url}")
                
                # Navigate to the follower's profile
                await self.page.goto(follower_url, timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(3)
                
                self.log(f"          ✅ Arrived at profile page")
                
                # Scroll to load buttons
                await self.page.evaluate("window.scrollBy(0, 400)")
                await asyncio.sleep(2)
                
                # Look for Confirm button on their profile
                result = await self.page.evaluate('''() => {
                    // AGGRESSIVE SEARCH: Try multiple selectors and methods
                    const possibleSelectors = [
                        '[role="button"]',
                        'button',
                        'div[role="button"]',
                        'a[role="button"]',
                        'div[aria-label]',
                        'span[role="button"]',
                        '[tabindex="0"]',
                        'div[class*="Button"]',
                        'span[class*="button"]'
                    ];
                    
                    const allElements = [];
                    possibleSelectors.forEach(selector => {
                        try {
                            const elements = document.querySelectorAll(selector);
                            allElements.push(...elements);
                        } catch (e) {
                            console.error('Selector failed:', selector, e);
                        }
                    });
                    
                    // Also get all divs, spans, buttons that might be styled as buttons
                    allElements.push(...document.querySelectorAll('div, span, button, a'));
                    
                    let foundButtons = [];
                    let confirmButton = null;
                    
                    for (const el of allElements) {
                        // Skip hidden elements
                        if (el.offsetParent === null) continue;
                        if (el.style.display === 'none') continue;
                        if (el.getAttribute('aria-disabled') === 'true') continue;
                        
                        const label = (el.getAttribute('aria-label') || '').toLowerCase();
                        const text = (el.innerText || '').toLowerCase().trim();
                        const textContent = (el.textContent || '').toLowerCase().trim();
                        
                        // Collect all button-like elements for debugging (limit text length)
                        if ((text.length > 0 && text.length < 100) || label.length > 0) {
                            // Only add unique buttons
                            const buttonInfo = {
                                text: text.substring(0, 50),
                                label: label.substring(0, 50),
                                tag: el.tagName,
                                role: el.getAttribute('role'),
                                classes: el.className ? el.className.substring(0, 50) : ''
                            };
                            
                            // Check if not duplicate
                            const isDuplicate = foundButtons.some(b => 
                                b.text === buttonInfo.text && 
                                b.label === buttonInfo.label && 
                                b.tag === buttonInfo.tag
                            );
                            
                            if (!isDuplicate && foundButtons.length < 100) {
                                foundButtons.push(buttonInfo);
                            }
                        }
                        
                        // Look for "Confirm" in multiple ways and variations
                        const hasConfirm = 
                            text === 'confirm' ||
                            text.startsWith('confirm') ||
                            text.includes('confirm request') ||
                            text.includes('accept request') ||
                            text.includes('respond to request') ||
                            label === 'confirm' ||
                            label.startsWith('confirm') ||
                            label.includes('confirm request') ||
                            label.includes('accept request') ||
                            textContent === 'confirm' ||
                            textContent.includes('confirm');
                        
                        // Avoid menu/navigation buttons
                        const isNotMenu = 
                            !label.includes('menu') &&
                            !label.includes('back') &&
                            !label.includes('close') &&
                            !label.includes('search') &&
                            !label.includes('settings') &&
                            !text.includes('menu') &&
                            !text.includes('back');
                        
                        if (hasConfirm && isNotMenu) {
                            console.log('🎯 FOUND CONFIRM:', {
                                text,
                                label,
                                tag: el.tagName,
                                role: el.getAttribute('role')
                            });
                            
                            confirmButton = el;
                            break;
                        }
                    }
                    
                    if (confirmButton) {
                        confirmButton.scrollIntoView({block: 'center', behavior: 'smooth'});
                        
                        // Try multiple click methods
                        try {
                            confirmButton.click();
                        } catch (e1) {
                            try {
                                confirmButton.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                            } catch (e2) {
                                console.error('Click failed:', e1, e2);
                                return {confirmed: false, error: 'click_failed', allButtons: foundButtons.slice(0, 30)};
                            }
                        }
                        
                        return {confirmed: true, allButtons: foundButtons.slice(0, 30)};
                    }
                    
                    return {confirmed: false, allButtons: foundButtons.slice(0, 30)};
                }''')
                
                if result.get('confirmed'):
                    accepted += 1
                    self.log(f"          ✅ Clicked Confirm button!")
                    await asyncio.sleep(3)
                else:
                    self.log(f"          ⚠️  No Confirm button found")
                    # Show all buttons we found for debugging
                    all_buttons = result.get('allButtons', [])
                    if all_buttons and len(all_buttons) > 0:
                        self.log(f"          📋 Found {len(all_buttons)} button-like elements:")
                        for i, btn in enumerate(all_buttons[:20], 1):
                            btn_text = btn.get('text', '')
                            btn_label = btn.get('label', '')
                            btn_tag = btn.get('tag', '')
                            btn_classes = btn.get('classes', '')
                            
                            # Show most useful info first
                            if btn_text and btn_text.strip():
                                display = f"Text: '{btn_text[:50]}'"
                            elif btn_label and btn_label.strip():
                                display = f"Label: '{btn_label[:50]}'"
                            else:
                                display = "(empty)"
                                
                            classes_info = f" [{btn_classes[:30]}]" if btn_classes else ""
                            self.log(f"              {i}. <{btn_tag}> {display}{classes_info}")
                    else:
                        self.log(f"          ⚠️  No buttons found at all!")
                    
                    # Take a screenshot for debugging
                    try:
                        import tempfile
                        screenshot_path = os.path.join(tempfile.gettempdir(), f"follower_profile_{int(time.time())}.png")
                        await self.page.screenshot(path=screenshot_path, full_page=True)
                        self.log(f"          📸 Screenshot saved: {screenshot_path}")
                    except Exception as e:
                        self.log(f"          ⚠️  Screenshot failed: {e}")
                
                # Small delay before next profile
                await asyncio.sleep(2)
            
            if accepted > 0:
                self.log(f"     🎉 Total accepted: {accepted}")
            else:
                self.log(f"     ℹ️  No requests confirmed")
            
            return accepted

        except Exception as e:
            self.log(f"     ❌ Error on followers page: {e}")
            self.log(f"        {traceback.format_exc()[:300]}")
            return accepted

    async def _click_confirm_buttons(self, max_click: int = 50) -> int:
        """Robust Confirm-button scanner on the CURRENT page.

        Scrolls through the page looking for Confirm / Accept buttons and
        clicks them.  Uses multiple passes with scrolling to handle
        Facebook's lazy-loaded content.

        Returns the number of buttons actually clicked.
        """
        total_clicked = 0

        JS_CLICK_CONFIRM = '''async () => {
            const candidates = [
                ...document.querySelectorAll('[role="button"]'),
                ...document.querySelectorAll('button'),
                ...document.querySelectorAll('a[role="button"]'),
                ...document.querySelectorAll('div[tabindex="0"]'),
                ...document.querySelectorAll('span[role="button"]'),
            ];

            const seen = new Set();
            let clicked = 0;

            for (const el of candidates) {
                if (clicked >= 50) break;
                if (seen.has(el)) continue;
                seen.add(el);

                const text  = (el.innerText  || '').trim();
                const label = (el.getAttribute('aria-label') || '').trim();
                const data-testid = (el.getAttribute('data-testid') || '').trim();
                const low_t = text.toLowerCase();
                const low_l = label.toLowerCase();
                const low_d = data-testid.toLowerCase();

                /* Skip invisible elements */
                if (el.offsetParent === null && el.getBoundingClientRect().width === 0) continue;
                if (el.getAttribute('aria-disabled') === 'true') continue;

                /* Match Confirm / Accept button — be lenient */
                const isConfirm =
                    (low_t === 'confirm' || low_t === 'accept' ||
                     low_t.startsWith('confirm') || low_t.startsWith('accept') ||
                     low_l.includes('confirm') || low_l.includes('accept') ||
                     low_d.includes('confirm') || low_d.includes('accept')) &&
                    /* exclude navigation / decorative */
                    !low_l.includes('menu') && !low_l.includes('back') &&
                    !low_l.includes('close') && !low_l.includes('search') &&
                    !low_t.includes('delete') && !low_l.includes('delete') &&
                    !low_t.includes('decline') && !low_l.includes('decline') &&
                    !low_t.includes('ignore');

                if (!isConfirm) continue;

                try {
                    el.scrollIntoView({block: 'center', behavior: 'smooth'});
                    await new Promise(r => setTimeout(r, 300));

                    /* try normal click first */
                    let clicked_ok = false;
                    try {
                        el.click();
                        clicked_ok = true;
                    } catch(_) {}

                    if (!clicked_ok) {
                        try {
                            el.dispatchEvent(new MouseEvent('click', {
                                bubbles: true, cancelable: true, view: window
                            }));
                            clicked_ok = true;
                        } catch(_) {}
                    }

                    if (!clicked_ok) {
                        /* Last resort: try the first child element */
                        const child = el.querySelector('[role="button"], button, a, span');
                        if (child) {
                            try { child.click(); clicked_ok = true; } catch(_) {}
                        }
                    }

                    if (clicked_ok) {
                        clicked++;
                        await new Promise(r => setTimeout(r, 500));
                    }
                } catch(_) {}
            }

            return clicked;
        }'''

        for attempt in range(10):
            if total_clicked >= max_click:
                break

            count = await self.page.evaluate(JS_CLICK_CONFIRM)

            if count > 0:
                total_clicked += count
                self.log(f"     ✅ Pass {attempt+1}: clicked {count} Confirm button(s)")
                await asyncio.sleep(1)
            else:
                await self.page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(1)
                count2 = await self.page.evaluate(JS_CLICK_CONFIRM)
                if count2 > 0:
                    total_clicked += count2
                    self.log(f"     ✅ Pass {attempt+1} (post-scroll): clicked {count2}")
                    await asyncio.sleep(1)
                else:
                    break

        return total_clicked

    async def _dump_page_buttons(self, label: str = "") -> None:
        """Debug helper: log all visible interactive elements on the current page."""
        if not self.debug:
            return
        info = await self.page.evaluate('''() => {
            const candidates = [
                ...document.querySelectorAll('[role="button"]'),
                ...document.querySelectorAll('button'),
                ...document.querySelectorAll('a'),
                ...document.querySelectorAll('div[tabindex]'),
            ];
            const seen = new Set();
            const results = [];
            for (const el of candidates) {
                if (seen.has(el)) continue;
                seen.add(el);
                const rect = el.getBoundingClientRect();
                if (rect.width === 0) continue;
                const text  = (el.innerText  || '').trim().substring(0, 60);
                const label = (el.getAttribute('aria-label') || '').trim().substring(0, 60);
                const tag   = el.tagName.toLowerCase();
                const role  = el.getAttribute('role') || '';
                const dtid  = (el.getAttribute('data-testid') || '').substring(0, 40);
                if (text || label) {
                    results.push({tag, role, text, label, dtid, w: Math.round(rect.width), h: Math.round(rect.height)});
                }
            }
            return results.slice(0, 40);
        }''')
        if info:
            self.log(f"  🔍 [{label}] Buttons on page ({len(info)} found):")
            for i, b in enumerate(info[:15], 1):
                self.log(f"      {i}. <{b.get('tag','')}> role={b.get('role','')} text=\"{b.get('text','')}\" label=\"{b.get('label','')}\" {b.get('w',0)}x{b.get('h',0)}")

    async def _detect_profile_status(self) -> str:
        """Detect relationship status with the profile currently loaded in self.page.

        Returns one of:
          'confirm'      – Confirm button visible (they sent us a request)
          'add_friend'   – Add Friend button visible (no connection yet)
          'cancel'       – Cancel / Request Sent visible (we sent a request)
          'friends'      – Already friends
          'message_only' – Message button but no Add Friend (likely friends / restricted)
          'unknown'
        """
        result = await self.page.evaluate('''() => {
            const candidates = [
                ...document.querySelectorAll('[role="button"]'),
                ...document.querySelectorAll('button'),
                ...document.querySelectorAll('a[role="button"]'),
                ...document.querySelectorAll('div[tabindex="0"]'),
                ...document.querySelectorAll('span[role="button"]'),
            ];

            const seen = new Set();
            let hasConfirm = false;
            let hasAddFriend = false;
            let hasCancel = false;
            let hasFriends = false;
            let hasMessage = false;

            const debugButtons = [];

            for (const el of candidates) {
                if (seen.has(el)) continue;
                seen.add(el);

                const text  = (el.innerText  || '').trim();
                const label = (el.getAttribute('aria-label') || '').trim();
                const dataTestId = (el.getAttribute('data-testid') || '').trim();
                const low_t = text.toLowerCase();
                const low_l = label.toLowerCase();
                const low_d = dataTestId.toLowerCase();
                const rect  = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                debugButtons.push(text.substring(0, 40) + ' | ' + label.substring(0, 40));

                /* Confirm / Accept — lenient matching */
                if ((low_t === 'confirm' || low_t === 'accept' ||
                     low_t.startsWith('confirm') || low_t.startsWith('accept') ||
                     low_l.includes('confirm') || low_l.includes('accept') ||
                     low_d.includes('confirm') || low_d.includes('accept')) &&
                    !low_l.includes('menu') && !low_l.includes('back') &&
                    !low_t.includes('delete') && !low_l.includes('delete') &&
                    !low_t.includes('decline') && !low_l.includes('decline') &&
                    !low_t.includes('ignore') && !low_l.includes('ignore'))
                    hasConfirm = true;

                /* Add Friend */
                if (low_l.includes('add friend') || low_t.includes('add friend') ||
                    low_d.includes('add friend'))
                    hasAddFriend = true;

                /* Cancel / Request Sent */
                if (low_l.includes('cancel') || low_t.includes('cancel') ||
                    low_l.includes('request sent') || low_t.includes('request sent') ||
                    low_d.includes('cancel'))
                    hasCancel = true;

                /* Already Friends */
                if ((low_t === 'friends' || low_l === 'friends' ||
                     low_d === 'friends') &&
                    !low_t.includes('add') && !low_l.includes('add'))
                    hasFriends = true;

                /* Message */
                if (low_t === 'message' || low_l.includes('send message') ||
                    low_d.includes('message'))
                    hasMessage = true;
            }

            return {
                hasConfirm, hasAddFriend, hasCancel, hasFriends, hasMessage,
                sampleButtons: debugButtons.slice(0, 20)
            };
        }''')

        if not isinstance(result, dict):
            return 'unknown'

        has_confirm = result.get('hasConfirm', False)
        has_add     = result.get('hasAddFriend', False)
        has_cancel  = result.get('hasCancel', False)
        has_friends = result.get('hasFriends', False)
        has_msg     = result.get('hasMessage', False)

        if self.debug:
            samples = result.get('sampleButtons', [])
            self.log(f"  🔍 Profile status: confirm={has_confirm} addFriend={has_add} cancel={has_cancel} friends={has_friends} message={has_msg}")
            if samples:
                self.log(f"     Buttons: {samples[:8]}")

        if has_confirm:      return 'confirm'
        if has_add:          return 'add_friend'
        if has_cancel:       return 'cancel'
        if has_friends:      return 'friends'
        if has_msg:          return 'message_only'
        return 'unknown'

    async def auto_accept_friend_requests(self, max_accept: int = 100) -> int:
        """Auto-accept pending friend requests via the friend-requests page.

        Navigates to Facebook's friend requests page and clicks Confirm on
        all visible pending requests.

        Returns:
            Number of friend requests accepted.
        """
        self.log(f"🔄 Auto-accepting friend requests — max: {max_accept}")
        accepted = 0

        try:
            # Navigate to friend requests page — try multiple URLs
            self.log(f"  📍 Navigating to friend requests page...")
            loaded = False
            for url in [
                "https://www.facebook.com/friends/requests/",
                "https://www.facebook.com/friends/requests/?type=received",
            ]:
                try:
                    await self.page.goto(url, timeout=25000, wait_until="networkidle")
                    await asyncio.sleep(3)
                    cur = self.page.url
                    if "facebook" in cur:
                        loaded = True
                        break
                except Exception:
                    continue

            if not loaded:
                self.log(f"  ❌ Could not load friend requests page")
                return 0

            # Debug: dump page title and buttons
            page_title = await self.page.title()
            self.log(f"  📄 Page title: {page_title}")
            await self._dump_page_buttons("friend-requests-page")

            # Scroll to top and wait for content
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(2)

            # Try clicking Confirm buttons
            for scroll_round in range(5):
                if accepted >= max_accept:
                    break

                count = await self._click_confirm_buttons(max_click=max_accept - accepted)
                if count > 0:
                    accepted += count
                    self.log(f"  ✅ Round {scroll_round+1}: accepted {count} (total: {accepted})")
                    await asyncio.sleep(2)
                else:
                    # Scroll down for more content
                    await self.page.evaluate("window.scrollBy(0, 600)")
                    await asyncio.sleep(1)

            # Also try Playwright locator as backup
            if accepted == 0:
                try:
                    confirm_btn = self.page.get_by_role("button", name="Confirm")
                    count = await confirm_btn.count()
                    if count > 0:
                        self.log(f"  🔍 Playwright found {count} Confirm button(s)")
                        for i in range(min(count, max_accept)):
                            try:
                                await confirm_btn.nth(i).click(timeout=3000)
                                accepted += 1
                                await asyncio.sleep(1)
                            except Exception:
                                pass
                except Exception as e:
                    self.log(f"  ⚠️  Playwright locator failed: {e}")

            if accepted > 0:
                self.log(f"  ✅ Accepted {accepted} request(s) from friend-requests page")
            else:
                self.log(f"  ℹ️  No Confirm buttons found on friend-requests page")

        except Exception as e:
            self.log(f"  ❌ Error during auto-accept: {e}")

        return accepted

    async def accept_friend_requests_by_visiting_profiles(self, profile_urls: dict[str, str]) -> list[str]:
        """Accept pending friend requests by visiting each sender's profile.

        When someone sends a friend request, visiting THEIR profile page shows a
        "Confirm" button. This method visits every known profile URL and clicks
        Confirm if present.

        Args:
            profile_urls: dict mapping profile_name -> facebook_url

        Returns:
            List of profile names whose requests were actually confirmed.
        """
        confirmed_names = []

        self.log(f"  📥 Accepting requests by visiting {len(profile_urls)} profile(s)...")

        for other_name, other_url in profile_urls.items():
            try:
                await self.page.goto(other_url, timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(4)

                # Scroll to trigger lazy-loaded profile action buttons
                await self.page.evaluate("window.scrollBy(0, 300)")
                await asyncio.sleep(1)

                status = await self._detect_profile_status()

                if status == 'confirm':
                    # Click Confirm button on this profile
                    clicked = await self._click_confirm_buttons(max_click=1)
                    if clicked > 0:
                        confirmed_names.append(other_name)
                        self.log(f"    ✅ Confirmed request from '{other_name}'")
                    else:
                        self.log(f"    ⚠️  '{other_name}' — Confirm detected but click failed")
                        await self._dump_page_buttons(f"confirm-fail-{other_name}")
                elif status == 'friends':
                    self.log(f"    ⏭️  '{other_name}' — already friends")
                elif status == 'cancel':
                    self.log(f"    ⏭️  '{other_name}' — request pending from us")
                elif status == 'add_friend':
                    self.log(f"    ⏭️  '{other_name}' — no request from them")
                else:
                    self.log(f"    ⏭️  '{other_name}' — status unclear ({status})")
                    await self._dump_page_buttons(f"unknown-{other_name}")

            except Exception as e:
                self.log(f"    ❌ Error visiting '{other_name}': {e}")

        self.log(f"  📥 Accepted {len(confirmed_names)} request(s) by visiting profiles")
        return confirmed_names

    async def accept_friend_requests_from_inbox(self, max_accept: int = 50) -> int:
        """Accept pending friend requests from the friend-requests page.

        Uses the same robust button detection as auto_accept_friend_requests.

        Args:
            max_accept: Maximum number of requests to accept.

        Returns:
            Number of requests accepted.
        """
        self.log(f"  📥 Accepting requests from friend-requests page...")
        accepted = 0

        try:
            for url in [
                "https://www.facebook.com/friends/requests/",
                "https://www.facebook.com/friends/requests/?type=received",
            ]:
                try:
                    await self.page.goto(url, timeout=25000, wait_until="networkidle")
                    await asyncio.sleep(3)
                    if "facebook" in self.page.url:
                        break
                except Exception:
                    continue

            await self._dump_page_buttons("inbox")
            accepted = await self._click_confirm_buttons(max_click=max_accept)
            if accepted > 0:
                self.log(f"     ✅ Accepted {accepted} request(s)")
            else:
                self.log(f"     ℹ️  No Confirm buttons found")
        except Exception as e:
            self.log(f"     ⚠️  Error: {e}")

        return accepted

    async def get_my_profile_url(self) -> str | None:
        """Get the current profile's Facebook URL.

        Navigates to /me and extracts the actual profile URL with user ID.

        Returns:
            Profile URL (e.g., https://www.facebook.com/username or https://www.facebook.com/profile.php?id=100012345) or None if failed.
        """
        self.log("Getting profile URL...")
        try:
            await self.page.goto("https://www.facebook.com/me",
                                 timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Get the actual URL after redirect
            profile_url = self.page.url
            
            # If we got profile.php, try to extract the user ID from the page
            if "profile.php" in profile_url:
                self.log("  Detected profile.php URL, extracting user ID...")
                
                # Method 1: Check if there's already an ID in the URL
                if "id=" in profile_url:
                    # Clean up the URL (remove extra query parameters except id)
                    match = re.search(r'[?&]id=(\d+)', profile_url)
                    if match:
                        user_id = match.group(1)
                        profile_url = f"https://www.facebook.com/profile.php?id={user_id}"
                        self.log(f"  Profile URL: {profile_url}")
                        return profile_url
                
                # Method 2: Extract user ID from page data
                user_id = await self.page.evaluate('''() => {
                    try {
                        // Try to find user ID in page data
                        const scripts = document.querySelectorAll('script');
                        for (const script of scripts) {
                            const text = script.textContent || '';
                            // Look for userID in various patterns
                            let match = text.match(/"userID":"(\\d+)"/);
                            if (match) return match[1];
                            match = text.match(/"USER_ID":"(\\d+)"/);
                            if (match) return match[1];
                            match = text.match(/"ownerID":"(\\d+)"/);
                            if (match) return match[1];
                            match = text.match(/\\bprofile_id["\\':]+(\\d+)/);
                            if (match) return match[1];
                        }
                        
                        // Check meta tags
                        const ogUrl = document.querySelector('meta[property="al:android:url"]');
                        if (ogUrl) {
                            const match = ogUrl.content.match(/profile\\/?(\\d+)/);
                            if (match) return match[1];
                        }
                        
                        // Check for links to the profile
                        const links = document.querySelectorAll('a[href*="profile.php?id="]');
                        if (links.length > 0) {
                            const match = links[0].href.match(/[?&]id=(\\d+)/);
                            if (match) return match[1];
                        }
                        
                        return null;
                    } catch (e) {
                        return null;
                    }
                }''')
                
                if user_id:
                    profile_url = f"https://www.facebook.com/profile.php?id={user_id}"
                    self.log(f"  ✅ Extracted user ID: {user_id}")
                    self.log(f"  Profile URL: {profile_url}")
                    return profile_url
                else:
                    self.log(f"  ⚠️ Could not extract user ID from page, using: {profile_url}")
                    return profile_url
            else:
                # Clean up the URL (remove query parameters for username-based URLs)
                if "?" in profile_url:
                    profile_url = profile_url.split("?")[0]
                
                self.log(f"  Profile URL: {profile_url}")
                return profile_url
            
        except Exception as e:
            self.log(f"  ❌ Failed to get profile URL: {e}")
            return None

    async def get_my_profile_name(self) -> str | None:
        """Get the current profile's Facebook display name.
        
        Navigates to /me and extracts the name shown on the profile.
        
        Returns:
            Profile name (e.g., "John Smith" or "Maria Garcia") or None if failed.
        """
        self.log("Getting Facebook profile name...")
        try:
            # Make sure we're on the profile page
            current_url = self.page.url
            if "/me" not in current_url and "profile.php" not in current_url:
                await self.page.goto("https://www.facebook.com/me",
                                     timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(2)
            
            # Extract the name from the page
            profile_name = await self.page.evaluate('''() => {
                // Helper function to check if text is valid profile name
                function isValidName(text) {
                    if (!text || text.length < 2 || text.length > 50) return false;
                    const lower = text.toLowerCase();
                    // Filter out Facebook UI text
                    const invalid = ['facebook', 'home', 'watch', 'marketplace', 'groups', 
                                    'gaming', 'menu', 'notifications', 'messages', 'profile',
                                    'settings', 'log out', 'create', 'edit', 'add', 'photo',
                                    'share a thought', 'what is on your mind', 'write something',
                                    'say something', 'post', 'share', 'update status'];
                    if (invalid.some(inv => lower === inv || lower.includes(inv))) return false;
                    // Should not be all lowercase (names have capitals)
                    if (text === text.toLowerCase() && text.length > 5) return false;
                    // Should not end with "..." (UI placeholder text)
                    if (text.endsWith('...') || text.endsWith('…')) return false;
                    return true;
                }
                
                // Method 1: Check meta tags first (most reliable)
                const ogTitle = document.querySelector('meta[property="og:title"]');
                if (ogTitle && ogTitle.content) {
                    const name = ogTitle.content.trim();
                    if (isValidName(name)) {
                        return name;
                    }
                }
                
                // Method 2: Look for h1 elements (usually contains the name)
                const h1Elements = document.querySelectorAll('h1');
                for (const h1 of h1Elements) {
                    const text = (h1.innerText || h1.textContent || '').trim();
                    if (isValidName(text) && !/\\d/.test(text)) {
                        return text;
                    }
                }
                
                // Method 3: Look for the profile name in specific profile elements
                // Facebook often has the name in a span near the profile picture
                const profileArea = document.querySelector('[data-pagelet="ProfileActions"]') || 
                                   document.querySelector('[data-pagelet="ProfileTilesFeed"]') ||
                                   document.body;
                                   
                const nameSpans = profileArea.querySelectorAll('span, h1, h2');
                for (const el of nameSpans) {
                    const text = (el.innerText || '').trim();
                    if (isValidName(text) && !/\\d{3}/.test(text) && !text.includes('@')) {
                        const rect = el.getBoundingClientRect();
                        // Should be visible, near the top, and reasonably sized (not tiny UI text)
                        if (rect.y > 0 && rect.y < 600 && rect.height > 15) {
                            // Additional check: should look like a name (has at least one space or capital letter)
                            if (text.includes(' ') || /[A-Z].*[A-Z]/.test(text)) {
                                return text;
                            }
                        }
                    }
                }
                
                // Method 4: Check page title as last resort
                const title = document.title;
                if (title) {
                    // Remove "| Facebook" or "- Facebook" suffix
                    const cleaned = title.replace(/[|\\-]\\s*Facebook.*$/i, '').trim();
                    if (isValidName(cleaned)) {
                        return cleaned;
                    }
                }
                
                return null;
            }''')
            
            if profile_name:
                self.log(f"  ✅ Facebook name: {profile_name}")
                return profile_name
            else:
                self.log(f"  ⚠️  Could not extract profile name")
                return None
                
        except Exception as e:
            self.log(f"  ❌ Failed to get profile name: {e}")
            return None

    async def _download_image_via_page(self, url: str, save_path: str) -> bool:
        """Download an image by navigating a temp page to its URL and capturing the response bytes.

        Uses Playwright's network layer directly — avoids CORS restrictions that
        would block in-page `fetch()` calls to cross-origin image CDNs.
        """
        temp_page = None
        try:
            temp_page = await self.context.new_page()
            response = await temp_page.goto(url, timeout=15000,
                                            wait_until="domcontentloaded")
            if response and response.ok:
                content = await response.body()
                with open(save_path, "wb") as f:
                    f.write(content)
                return True
            return False
        except Exception:
            return False
        finally:
            if temp_page:
                try:
                    await temp_page.close()
                except Exception:
                    pass

    async def scrape_pinterest_images(self, query: str, count: int = 10, save_dir: str = None) -> list[str]:
        """Scrape images from Pinterest search and save to a temp directory.

        Opens a temporary page within the same browser context to search
        Pinterest, scroll to load images, extract image URLs, and download
        them via Playwright's network layer (sidestepping CORS restrictions).
        Returns a list of saved file paths.

        Args:
            query: Search term (e.g. "profile picture aesthetic").
            count: How many images to attempt to download (max 20).
            save_dir: Optional custom directory to save images. If None, creates a temp dir.

        Returns:
            List of absolute paths to saved images.
        """
        import tempfile

        if save_dir is None:
            save_dir = tempfile.mkdtemp(prefix="pinterest_")
        else:
            os.makedirs(save_dir, exist_ok=True)
            
        search_url = f"https://www.pinterest.com/search/pins/?q={query.replace(' ', '%20')}"
        self.log(f"Scraping Pinterest for '{query}'...")

        saved_paths: list[str] = []
        pinterest_page = None

        try:
            # Check if context is still valid
            if not self.context:
                self.log("  ❌ Browser context not available")
                return []
            
            # Create a temporary page for Pinterest
            pinterest_page = await self.context.new_page()
            
            # Try to load Pinterest with retry logic (sometimes times out)
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    self.log(f"  🌐 Loading Pinterest search (attempt {attempt + 1}/{max_retries})...")
                    await pinterest_page.goto(search_url, timeout=30000,  # Reduced timeout to 30s
                                            wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    break  # Success!
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.log(f"  ⚠️  Timeout, retrying...")
                        await asyncio.sleep(2)
                    else:
                        raise  # Give up after retries

            # Close any login popup if it appears
            try:
                close_btn = pinterest_page.locator('[aria-label="Close"]').first
                if await close_btn.count() > 0 and await close_btn.is_visible():
                    await close_btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Scroll to load more images (5 scrolls to get enough images)
            for i in range(5):
                try:
                    await pinterest_page.evaluate("window.scrollBy(0, 2000)")
                    await asyncio.sleep(1.5)
                except:
                    break

            # Extract image URLs - prioritize large/original sizes
            image_urls = await pinterest_page.evaluate('''(limit) => {
                const urls = new Set();
                const imgs = document.querySelectorAll('img');
                
                // Strategy 1: Look for 'originals' (full resolution)
                for (const img of imgs) {
                    const src = img.getAttribute('src') || img.getAttribute('srcset') || '';
                    if (src.includes('pinimg.com') && src.includes('/originals/')) {
                        urls.add(src);
                    }
                }
                
                console.log('Found', urls.size, 'original images');
                
                // Strategy 2: If not enough originals, upgrade medium-sized images to largest available
                if (urls.size < limit) {
                    for (const img of imgs) {
                        if (urls.size >= limit) break;
                        
                        const src = img.getAttribute('src') || '';
                        if (!src.includes('pinimg.com') || src.includes('.svg')) continue;
                        
                        // Skip tiny thumbnails (60x, 75x, 170x, 236x)
                        if (src.includes('/60x/') || src.includes('/75x/') || 
                            src.includes('/170x/') || src.includes('/236x/')) {
                            continue;
                        }
                        
                        // Upgrade to largest size available (1200x is best after originals)
                        let largeUrl = src
                            .replace('/474x/', '/1200x/')
                            .replace('/564x/', '/1200x/')
                            .replace('/736x/', '/1200x/');
                        
                        // If still has size marker, try to get originals
                        const sizePattern = /\\/\\d+x\\d+\\//;
                        if (sizePattern.test(largeUrl)) {
                            // Try to construct originals URL by removing size
                            const originalsUrl = largeUrl.replace(sizePattern, '/originals/');
                            urls.add(originalsUrl);
                        } else {
                            urls.add(largeUrl);
                        }
                    }
                }
                
                console.log('Total URLs after upgrade:', urls.size);
                
                // Strategy 3: Last resort - try any pinimg URLs but upgrade them
                if (urls.size === 0) {
                    console.log('WARNING: No good images found, using thumbnails and upgrading');
                    for (const img of imgs) {
                        if (urls.size >= limit) break;
                        
                        const src = img.getAttribute('src') || '';
                        if (src.includes('pinimg.com') && !src.includes('.svg')) {
                            // Force upgrade to 1200x or originals
                            const sizePattern = /\\/\\d+x\\d+\\//;
                            const upgraded = src
                                .replace(sizePattern, '/originals/')
                                .replace('/originals/', '/1200x/');  // Fallback if originals doesn't work
                            urls.add(upgraded);
                        }
                    }
                }
                
                return Array.from(urls).slice(0, limit);
            }''', count)

            self.log(f"  Found {len(image_urls)} Pinterest image(s)")

            if not image_urls:
                self.log("  ⚠️ No Pinterest images found")
                return []

            # Download images using Playwright's network layer (no CORS issues)
            # Try to download up to the requested count
            download_limit = min(len(image_urls), count * 2)  # Try up to 2x count to account for filtering
            
            for idx, url in enumerate(image_urls):
                if len(saved_paths) >= count:  # Stop once we have the requested count
                    break
                if idx >= download_limit:  # But don't try more than limit
                    break
                    
                # Determine extension from URL
                url_lower = url.lower()
                if ".png" in url_lower:
                    ext = ".png"
                elif ".gif" in url_lower:
                    ext = ".gif"
                elif ".webp" in url_lower:
                    ext = ".webp"
                elif ".jpg" in url_lower or ".jpeg" in url_lower:
                    ext = ".jpg"
                else:
                    ext = ".jpg"  # default

                fpath = os.path.join(save_dir, f"pin_{idx}{ext}")
                self.log(f"  Downloading image {idx+1}...")
                ok = await self._download_image_via_page(url, fpath)
                if ok:
                    size = os.path.getsize(fpath)
                    
                    # Validate image dimensions - prefer square images close to 720x720px
                    # Facebook profile picture specs:
                    # - Optimal: 720×720px
                    # - Minimum: 180×180px (but we prefer 400×400+ for quality)
                    # - Display: 170×170px desktop, 128×128px mobile (shown as circle)
                    try:
                        from PIL import Image
                        with Image.open(fpath) as img:
                            width, height = img.size
                            aspect_ratio = width / height if height > 0 else 0
                            
                            # Calculate how square the image is (1.0 = perfect square)
                            square_score = min(width, height) / max(width, height) if max(width, height) > 0 else 0
                            
                            # Skip images smaller than minimum Facebook requirement
                            # Facebook minimum is 180x180, we accept anything above that
                            if width < 180 or height < 180:
                                self.log(f"    ⚠️  Too small ({width}x{height}px) - need 180x180+ minimum")
                                try:
                                    os.remove(fpath)
                                except:
                                    pass
                                continue
                            
                            # Accept most images - Facebook can crop/resize
                            # We only reject extremely non-square images (very tall/wide)
                            if square_score < 0.60:  # Accept anything 60%+ square (e.g., 600x1000 = 0.60)
                                self.log(f"    ⚠️  Too rectangular ({width}x{height}px, ratio {aspect_ratio:.2f}) - prefer more square images")
                                try:
                                    os.remove(fpath)
                                except:
                                    pass
                                continue
                            
                            # Calculate quality score (prefer images close to 720x720)
                            optimal_size = 720
                            size_diff = abs(min(width, height) - optimal_size)
                            quality_score = 100 - (size_diff / optimal_size * 100)
                            
                            self.log(f"    ✅ Saved ({size // 1024}KB, {width}x{height}px, square={square_score:.2f}, quality={quality_score:.0f}%)")
                            saved_paths.append(fpath)
                    except ImportError:
                        # If PIL not available, accept based on file size
                        # Images >= 50KB are likely large enough for profile pics
                        if size >= 50000:  # 50KB minimum (increased from 20KB)
                            saved_paths.append(fpath)
                            self.log(f"    ✅ Saved ({size // 1024}KB)")
                        else:
                            self.log(f"    ⚠️  Too small ({size // 1024}KB) - need 50KB+ for quality")
                            try:
                                os.remove(fpath)
                            except:
                                pass
                    except Exception as verify_err:
                        # If validation fails, keep the image anyway
                        self.log(f"    ⚠️  Could not verify size: {verify_err}")
                        saved_paths.append(fpath)
                        self.log(f"    ✅ Saved ({size // 1024}KB)")
                else:
                    self.log(f"    ❌ Failed")

            self.log(f"  Downloaded {len(saved_paths)} image(s)")

        except Exception as e:
            self.log(f"  ❌ Pinterest scraping error: {e}")
        finally:
            if pinterest_page:
                try:
                    await pinterest_page.close()
                except Exception:
                    pass

        return saved_paths

    async def set_profile_picture(self, image_path: str) -> bool:
        """Upload and set a profile picture on Facebook.

        Simple, direct approach:
        1. Navigate to profile page
        2. Open the profile picture upload dialog (if not already open)
        3. Upload the image via the file input
        4. Click Save
        """
        self.log(f"Setting profile picture from: {image_path}")

        if not os.path.isfile(image_path):
            self.log(f"❌ Image file not found: {image_path}")
            return False

        # Check image dimensions
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size
                self.log(f"  Image size: {width}x{height}px")

                if width < 180 or height < 180:
                    self.log(f"  ❌ Image TOO SMALL ({width}x{height}px)")
                    self.log(f"  ❌ Facebook requires minimum 180×180px")
                    return False
        except Exception as e:
            self.log(f"  ⚠️  Could not check image dimensions: {e}")

        try:
            # STEP 1: Navigate to profile page
            self.log("  📍 Step 1: Navigate to profile page...")
            await self.page.goto("https://www.facebook.com/me",
                                 timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # STEP 2: Find the file input (appears once the upload dialog is open)
            self.log("  📍 Step 2: Locating profile picture file input...")
            file_input = self.page.locator('input[type="file"]').first
            if await file_input.count() == 0:
                # Open the "Choose profile picture" menu first
                self.log("  Opening 'Choose profile picture' dialog...")
                menu_btn = await self._find(
                    css=[
                        '[role="menuitem"]:has-text("Choose profile picture")',
                        '[role="button"]:has-text("Choose profile picture")',
                        '[aria-label="Choose profile picture"]',
                    ],
                    text="Choose profile picture",
                    timeout=8,
                    visible_only=True,
                )
                if not menu_btn:
                    self.log("  ❌ Could not open profile picture upload dialog")
                    return False
                await menu_btn.click(force=True)
                await asyncio.sleep(3)
                file_input = self.page.locator('input[type="file"]').first
                if await file_input.count() == 0:
                    self.log("  ❌ File input not found after opening dialog")
                    return False

            # STEP 3: Upload the image
            self.log("  📍 Step 3: Uploading image...")
            await file_input.set_input_files(image_path)
            self.log("  ✅ Image uploaded to file input")
            await asyncio.sleep(2)

            # STEP 4: Click Save
            self.log("  📍 Step 4: Saving changes...")
            save_btn = await self._find(
                css=[
                    '[role="button"]:has-text("Save")',
                    'button:has-text("Save")',
                    '[data-testid="profile_pic_save"]',
                ],
                text="Save",
                timeout=8,
                visible_only=True,
            )
            if save_btn:
                await save_btn.click(force=True)
                await asyncio.sleep(2)
                self.log("  ✅ Profile picture saved!")
            else:
                self.log("  ⚠️  Save button not found — image may auto-save")

            return True

        except Exception as e:
            self.log(f"  ❌ Failed: {e}")
            return False


    async def update_profile_bio(self, bio: str) -> bool:
        """Update the profile's About / Intro section with a bio.

        Args:
            bio: The bio text to set.

        Returns:
            True if the bio was updated.
        """
        if not bio or not bio.strip():
            return True
        bio = bio.strip()
        self.log(f"Updating profile bio: '{bio[:60]}...'")

        try:
            # Navigate to profile's About page
            await self.page.goto("https://www.facebook.com/me/about?section=bio",
                                 timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # Look for a text input or editable area related to bio/intro
            bio_input = await self._find(
                css=[
                    'div[role="textbox"][aria-label*="bio" i]',
                    'div[role="textbox"][aria-label*="about" i]',
                    'textarea[aria-label*="bio" i]',
                    'textarea[aria-label*="about" i]',
                    'div[contenteditable="true"]:has-text("Bio")',
                    'input[aria-label*="bio" i]',
                    'input[aria-label*="about" i]',
                ],
                timeout=10,
                visible_only=True,
            )

            if not bio_input:
                # Try the intro section edit flow
                self.log("Bio input not directly visible — trying to navigate to intro edit...")
                await self.page.goto("https://www.facebook.com/me/about",
                                     timeout=30000, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # Find an "Edit" button near the intro section
                edit_btn = await self._find(
                    css=[
                        '[aria-label*="Edit" i]:has-text("Intro")',
                        '[aria-label*="Edit" i]:has-text("About")',
                        'div[role="button"]:has-text("Edit"):has-text("Intro")',
                        'div[role="button"]:has-text("Edit Details")',
                    ],
                    timeout=8,
                    visible_only=True,
                )
                if not edit_btn:
                    self.log("Could not find bio edit button")
                    await self._dump_page_buttons("bio_edit")
                    return False

                await edit_btn.click(force=True)
                await asyncio.sleep(2)

                # Now look for the text input
                bio_input = await self._find(
                    css=[
                        'div[role="textbox"][contenteditable="true"]',
                        'textarea',
                        'input[type="text"]',
                    ],
                    timeout=8,
                    visible_only=True,
                )

            if not bio_input:
                self.log("Could not find bio input field")
                await self._dump_page_buttons("bio_input")
                return False

            # Clear and type the bio
            await bio_input.click(force=True)
            await asyncio.sleep(0.3)
            await bio_input.fill("")
            await asyncio.sleep(0.2)
            await self.page.keyboard.type(bio, delay=random.randint(40, 100))
            await asyncio.sleep(random.uniform(0.5, 1))

            # Look for Save button
            save_btn = await self._find(
                css=[
                    'div[role="button"]:has-text("Save")',
                    'div[role="button"]:has-text("Done")',
                    'button:has-text("Save")',
                    'button:has-text("Done")',
                ],
                timeout=5,
                visible_only=True,
            )

            if save_btn:
                await save_btn.click(force=True)
                await asyncio.sleep(2)
                self.log("Bio saved!")
            else:
                self.log("Bio typed — save button not found (may auto-save)")

            return True

        except Exception as e:
            self.log(f"Failed to update bio: {e}")
            return False

    async def auto_setup_profile(self, target_friends: int = 50,
                                  pinterest_query: str = None,
                                  bio: str = None,
                                  connect_friends: bool = True,
                                  profile_pic_path: str = None) -> dict:
        """Run the full auto-setup flow for a Facebook profile.

        1. Checks if the account has friends → auto-adds if below target_friends
        2. Checks if profile has picture → fills from Pinterest if missing

        If profile_pic_path is provided, that exact image is uploaded directly
        instead of auto-selecting from Pinterest results.

        Args:
            target_friends: Minimum friends to aim for (stops early if reached).
            pinterest_query: Search term for Pinterest images (used when no path is given).
            bio: Bio text to set if the profile has no bio.
            profile_pic_path: Exact image path to use for profile picture.

        Returns:
            dict with results of each check.
        """
        self.log("=" * 50)
        self.log("🚀 AUTO SETUP PROFILE")
        self.log("=" * 50)

        result = {
            "friends_before": 0,
            "friends_after": 0,
            "friends_added": 0,
            "had_profile_pic": False,
            "profile_pic_set": False,
            "pinterest_images_downloaded": 0,
            "pending_requests_accepted": 0,
            "had_bio": False,
            "bio_updated": False,
        }

        # ── Step 0: Accept ANY pending friend requests FIRST ──
        self.log(f"\n── Step 0: Checking for Pending Friend Requests ──")
        try:
            pending_accepted = await self.auto_accept_friend_requests(max_accept=100)
            result["pending_requests_accepted"] = pending_accepted
            if pending_accepted > 0:
                self.log(f"✅ Accepted {pending_accepted} pending friend request(s)")
            else:
                self.log(f"ℹ️  No pending friend requests to accept")
        except Exception as e:
            self.log(f"⚠️  Could not check pending requests: {e}")
            result["pending_requests_accepted"] = 0

        # ── Step 1: Check friends count ──────────────────────
        self.log(f"\n── Step 1: Checking Friends (target: {target_friends}) ──")
        friends_before = await self.check_friends_count()
        result["friends_before"] = friends_before

        if friends_before < target_friends:
            needed = target_friends - friends_before
            
            # Skip auto-add if connect_friends is disabled OR target is low (≤5)
            # This is useful when profiles will be connected to each other later
            if not connect_friends:
                self.log(f"Only {friends_before} friends (target: {target_friends})")
                self.log(f"⏭️  Skipping friend suggestions (connect_friends disabled)")
                result["friends_added"] = 0
                result["friends_after"] = friends_before
            elif target_friends <= 5:
                self.log(f"Only {friends_before} friends (target: {target_friends})")
                self.log(f"⏭️  Skipping friend suggestions (profiles will connect to each other)")
                result["friends_added"] = 0
                result["friends_after"] = friends_before
            else:
                self.log(f"Only {friends_before} friends — adding {needed} more...")
                sent = await self.auto_add_friends(target_count=needed, max_requests=200)
                result["friends_added"] = sent
                result["friends_after"] = await self.check_friends_count()
                self.log(f"Friends added: {sent} (now ~{result['friends_after']})")
        else:
            self.log(f"✅ Already has {friends_before} friends — skipping")
            result["friends_after"] = friends_before

        # ── Step 2: Check profile setup ──────────────────────
        self.log("\n── Step 2: Checking Profile Setup ──")
        profile = await self.check_profile_setup()
        result["had_profile_pic"] = profile["has_profile_pic"]

        needs_pic = not profile["has_profile_pic"]

        if needs_pic:
            if profile_pic_path:
                self.log(f"📥 Using assigned image: {os.path.basename(profile_pic_path)}")
                images = [profile_pic_path]
                result["pinterest_images_downloaded"] = 1
            elif pinterest_query:
                self.log(f"🔍 Scraping Pinterest for '{pinterest_query}'...")
                images = await self.scrape_pinterest_images(pinterest_query, count=10)
                result["pinterest_images_downloaded"] = len(images)
            else:
                self.log("⚠️  No image path or Pinterest query provided - skipping profile picture")
                images = []
                result["pinterest_images_downloaded"] = 0

            if images:
                self.log("\n── Setting Profile Picture ──")
                pic_path = images[0]
                self.log(f"   Uploading: {os.path.basename(pic_path)}")
                pic_ok = await self.set_profile_picture(pic_path)
                result["profile_pic_set"] = pic_ok
                if pic_ok:
                    self.log("✅ Profile picture uploaded successfully!")
                else:
                    self.log("❌ Failed to upload profile picture")
            else:
                self.log("⚠️  No images available - skipping profile picture")
                result["profile_pic_set"] = False
        else:
            self.log("✅ Profile picture already present — skipping")

        # ── Step 3: Update bio ──────────────────────────────
        self.log("\n── Step 3: Checking Bio ──")
        result["had_bio"] = profile["has_bio"]

        if bio and not profile["has_bio"]:
            self.log(f"  📝 Setting bio...")
            bio_ok = await self.update_profile_bio(bio)
            result["bio_updated"] = bio_ok
            if bio_ok:
                self.log("✅ Bio updated successfully!")
            else:
                self.log("❌ Failed to update bio")
        elif profile["has_bio"]:
            self.log("✅ Bio already present — skipping")
            result["bio_updated"] = False
        else:
            self.log("⏭️  No bio provided — skipping")
            result["bio_updated"] = False

        # ── Summary ──────────────────────────────────────────
        self.log("=" * 50)
        self.log("AUTO SETUP COMPLETE")
        self.log(f"  Pending requests accepted: {result['pending_requests_accepted']}")
        self.log(f"  Friends: {result['friends_before']} → +{result['friends_added']} ({result['friends_after']})")
        self.log(f"  Profile pic: {'✅' if result['profile_pic_set'] else ('⏭️ already had' if result['had_profile_pic'] else '❌')}")
        self.log(f"  Bio: {'✅' if result['bio_updated'] else ('⏭️ already had' if result['had_bio'] else '❌')}")
        self.log("=" * 50)

        return result

    async def cleanup(self):
        await self.quit()

    async def quit(self):
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
            self.page = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
        gc.collect()

    # ── Credential login ─────────────────────────────────

    async def login_with_credentials(self, email: str, password: str,
                                     wait_for_2fa: bool = True) -> tuple[bool, str]:
        """Fill in email/password on the Facebook login page and submit.
        Returns (ok, message). On success, session cookies are stored in the profile.

        wait_for_2fa keeps the assisted behaviour: on a checkpoint or 2FA page
        it waits up to 120 s for a person to finish it in the visible window.
        Unattended callers (the headless re-login the web app runs) pass False
        - nobody can answer, so the wait only ever expires, and the verdict is
        the same one the classification already gives."""
        # reCAPTCHA and the 2FA challenge need images and fonts. With blocking
        # on, the widget fails with "Cannot contact reCAPTCHA" - the same
        # failure class as the comment composer (see _auto_comment).
        self._block_resources = False

        self.log("Navigating to Facebook login page...")
        for attempt in range(2):
            try:
                await self.page.goto("https://www.facebook.com/login.php",
                                     timeout=30000, wait_until="load")
                await asyncio.sleep(random.uniform(3, 4))
                # Verify the page is actually interactive
                ready = await self.page.evaluate("document.readyState === 'complete'")
                if not ready:
                    await asyncio.sleep(2)
                break
            except Exception as e:
                if attempt == 1:
                    return False, f"Failed to load login page: {e}"
                self.log(f"Retrying navigation... ({e})")
                await asyncio.sleep(3)

        # Land on the page like a reader, not like a script that starts
        # typing the instant load fires.
        await human_input.settle(self.page)

        # A signed-out-but-remembered profile lands on the account chooser,
        # which has no email field at all. Step through it first.
        await self._dismiss_account_chooser()

        # Fill email with retry
        email_input = None
        for attempt in range(2):
            self.log(f"Filling email... (attempt {attempt+1})")
            try:
                # Verify page is still alive
                _ = await self.page.title()
                email_input = await self._find(
                    css=['input[name="email"]', 'input[type="text"]', 'input#email'],
                    timeout=8,
                    visible_only=True,
                )
                if email_input:
                    break
                if attempt == 0:
                    self.log("Email input not found, re-navigating to login page...")
                    await self.page.goto("https://www.facebook.com/login.php",
                                         timeout=30000, wait_until="load")
                    await asyncio.sleep(random.uniform(2, 3))
                    await self._dismiss_account_chooser()
            except Exception as e:
                if attempt == 1:
                    await self._dump_page_buttons("login_email")
                    return False, f"Email input not found after retry: {e}"
                self.log(f"Page issue, retrying... ({e})")
                await asyncio.sleep(3)

        if not email_input:
            await self._dump_page_buttons("login_email")
            return False, "Email input not found"

        try:
            await human_input.type_text(self.page, email_input, email)
            await asyncio.sleep(random.uniform(0.3, 0.8))
        except Exception as e:
            return False, f"Could not fill email: {e}"

        # Fill password
        self.log("Filling password...")
        try:
            pass_input = await self._find(
                css=['input[name="pass"]', 'input[type="password"]', 'input#pass'],
                timeout=5,
                visible_only=True,
            )
            if not pass_input:
                return False, "Password input not found"
            await human_input.type_text(self.page, pass_input, password)
            await asyncio.sleep(random.uniform(0.4, 1.1))
        except Exception as e:
            return False, f"Could not fill password: {e}"

        # Click Login button
        self.log("Clicking Login button...")
        try:
            login_btn = await self._find(
                css=[
                    'button[name="login"]',
                    'button[type="submit"]',
                    'input[type="submit"]',
                    '[role="button"]:has-text("Log In")',
                    '[role="button"]:has-text("Log in")',
                ],
                text="Log In",
                timeout=8,
                visible_only=True,
            )
            if not login_btn:
                # Fallback: try pressing Enter on the password field
                self.log("Login button not found, trying Enter key...")
                await self.page.keyboard.press("Enter")
            else:
                # A pause before submitting, then a real pointer press: the
                # button used to be hit at its exact centre with no travel.
                await asyncio.sleep(random.uniform(0.3, 0.9))
                if not await human_input.click(self.page, login_btn):
                    await login_btn.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    await login_btn.click(force=True)
        except Exception as e:
            return False, f"Could not click Login button: {e}"

        # Wait for post-login navigation
        self.log("Waiting for login to complete...")
        await asyncio.sleep(random.uniform(3, 5))

        # "I'm not a robot" can come up on the form or right after submitting.
        # An unanswered one leaves the page sitting on the login screen, which
        # used to be reported as a wrong password.
        captcha = await self.handle_recaptcha()
        if captcha == "needs human":
            return False, "captcha - solve it in the window"
        if captcha == "solved":
            await asyncio.sleep(random.uniform(2, 4))
            if not await self._is_logged_in(timeout=5):
                # The captcha was the gate on the form: submitting again is
                # what actually logs in.
                try:
                    await self.page.keyboard.press("Enter")
                    await asyncio.sleep(random.uniform(3, 5))
                except Exception:
                    pass

        # Check for 2FA / checkpoint page
        try:
            current_url = self.page.url.lower()
        except Exception:
            current_url = ""

        # "two_step_verification" is Facebook's current 2FA path and matches
        # none of the older keywords ("twofactor" is a different string), so
        # a 2FA page used to read as a completed login.
        # Real gates only. "/login/device-based/regular/login/" is a step of
        # the ORDINARY login flow, and a bare "review" matches pages that are
        # not gates at all; with the unattended path no longer waiting out a
        # 120 s human timer, either one turned a successful login into
        # "CHECKPOINT OR VERIFICATION REQUIRED".
        checkpoint_keywords = ["checkpoint", "twofactor", "two_step_verification",
                               "approvals", "confirmemail"]
        if any(kw in current_url for kw in checkpoint_keywords):
            # Name the gate. "two_step_verification" is an authenticator and
            # "confirmemail" is an inbox; recording both as CHECKPOINT told
            # the operator nothing about what the account actually needs.
            gate = ("two-factor authentication required"
                    if ("two_step_verification" in current_url
                        or "twofactor" in current_url
                        or "approvals" in current_url)
                    else "email confirmation required"
                    if "confirmemail" in current_url
                    else "checkpoint required")
            self.log("\u26a0\ufe0f 2FA / checkpoint detected! Complete it manually in the browser.")
            self.log(f"Current URL: {current_url}")
            if not wait_for_2fa:
                # Unattended: nobody can answer a real 2FA prompt, so the
                # 120 s human timer is pointless - but a gate URL can still
                # clear itself in a second or two, and judging the first
                # frame is what reported working accounts as gated. Give it a
                # short grace period, then take the verdict.
                for _ in range(int(self.UNATTENDED_GATE_GRACE_S)):
                    await asyncio.sleep(1)
                    try:
                        url_now = self.page.url.lower()
                    except Exception:
                        continue
                    if any(kw in url_now for kw in checkpoint_keywords):
                        continue
                    if "login" in url_now or "password" in url_now:
                        continue
                    if "facebook.com" in url_now and await self._is_logged_in(timeout=3):
                        self.log("Login completed after the redirect cleared")
                        return True, "Logged in successfully"
                return False, f"{gate} - finish it manually"
            self.log("Waiting up to 120s for you to finish 2FA...")

            # Wait for user to complete 2FA and reach facebook.com
            for _ in range(120):
                await asyncio.sleep(1)
                try:
                    url_now = self.page.url.lower()
                    if any(kw in url_now for kw in checkpoint_keywords):
                        continue
                    if "login" in url_now or "password" in url_now:
                        continue
                    # Check if we're on a facebook page that isn't login
                    if "facebook.com" in url_now:
                        # Verify we're truly logged in
                        logged_in = await self._is_logged_in(timeout=3)
                        if logged_in:
                            self.log("2FA completed successfully!")
                            return True, "Logged in (after 2FA)"
                except Exception:
                    continue
            else:
                return False, f"{gate} - timed out after 120s"

        # Normal login — verify we're logged in
        logged_in = await self._is_logged_in(timeout=15)
        if logged_in:
            self.log("Login successful!")
            return True, "Logged in successfully"
        else:
            # Check for error messages
            try:
                error_el = await self._find(
                    css=[
                        '[role="alert"]',
                        '#error_box',
                        '.uiError',
                        'div:has-text("incorrect")',
                        'div:has-text("didn\'t match")',
                    ],
                    timeout=3,
                    visible_only=True,
                )
                if error_el:
                    err_text = (await error_el.inner_text() or "").strip()[:100]
                    return False, f"Login failed: {err_text}"
            except Exception:
                pass
            # No error box: say where the browser actually ended up, or the
            # sheet records every one of these as "unknown not logged in" and
            # the operator cannot tell a stuck form from a gate.
            try:
                where = self.page.url.lower()
            except Exception:
                where = ""
            if "login" in where or "/login.php" in where:
                return False, ("still on the login form - wrong password, or "
                               "Facebook rejected the attempt")
            if "facebook.com" not in where:
                return False, f"left Facebook for {where[:80] or 'a blank page'}"
            self.log(f"  unexplained login failure at {where[:120]}")
            for url in await self._frame_urls():
                if url and "facebook.com" not in url:
                    self.log(f"  third-party frame: {url[:120]}")
            return False, "Login failed — check credentials or complete login manually"

    # ── Auto React ────────────────────────────────────────

    REACTION_LABELS = {
        "like": "Like",
        "love": "Love",
        "care": "Care",
        "haha": "Haha",
        "wow": "Wow",
        "sad": "Sad",
        "angry": "Angry",
    }

    async def _auto_react(self, post_url: str | None, reaction: str | None) -> tuple[bool, str]:
        """React to the post with the given reaction type.
        
        Returns (ok, message) where message describes what actually happened.
        
        NOTE: URL auto-fixing is now handled at the batch level before this function is called.
        """
        if not reaction:
            return True, "No reaction specified"
        reaction = reaction.strip().lower()
        if reaction not in self.REACTION_LABELS:
            self.log(f"Unknown reaction '{reaction}', skipping")
            return True, f"Unknown reaction '{reaction}'"

        if post_url:
            self.log(f"📍 Navigating to post for reaction...")
            # Normalize URL: add scheme, convert mobile -> desktop so the reaction
            # UI renders in desktop layout (mobile requires touch long-press).
            if not post_url.startswith("http"):
                post_url = f"https://www.facebook.com/{post_url}"
            post_url = post_url.replace("m.facebook.com", "www.facebook.com")
            post_url = post_url.replace("mobile.facebook.com", "www.facebook.com")
            self.log(f"   Target URL: {post_url}")
            try:
                # Navigate to the post URL with retries — a single network blip
                # must not fail the reaction. Use "domcontentloaded" (faster).
                for attempt in range(3):
                    try:
                        await self.page.goto(post_url, timeout=30000, wait_until="domcontentloaded")
                        break
                    except Exception as e:
                        if attempt < 2:
                            self.log(f"   Navigation attempt {attempt + 1}/3 failed: {e} — retrying...")
                            await asyncio.sleep(3)
                            continue
                        self.log(f"Could not navigate for reaction: {e}")
                        return False, f"Navigation failed: {e}"

                # If the session is stale we land on a login page — fail clearly
                if not await self._is_logged_in(timeout=10):
                    access_status = await self._classify_account_access()
                    self.log(f"Account diagnosis: {access_status}")
                    self.log("Not logged in — cannot react")
                    return False, f"Not logged in ({access_status.replace('_', ' ')})"

                # Wait for page to stabilize
                await asyncio.sleep(random.uniform(2, 3))
                
                # Verify we're on the correct URL
                current_url = self.page.url
                self.log(f"   Current URL: {current_url}")
                
                # rdid is Facebook's own redirect token, added to every
                # /share/ link it resolves to a permalink. It says nothing
                # about WHICH post was opened, so warning about it made every
                # ordinary share link look like a hijacked navigation. What
                # matters is the post identity, checked below against the
                # landed URL with tracking parameters stripped.
                current_url = _without_tracking(current_url)
                
                # What the requested URL says the post is. A /share/p/ or
                # /share/v/ link says nothing: it is a token Facebook
                # exchanges for the permalink, so there is no identity to
                # compare and comparing anyway reported every share link as a
                # redirect to the wrong post.
                expected_story_fbid = None
                expected_post_id = None
                expected_profile_id = None

                if "/share/" in post_url:
                    self.log(f"   Share link resolved to: {current_url[:110]}")
                else:
                    if "story_fbid=" in post_url:
                        expected_story_fbid = post_url.split("story_fbid=")[1].split("&")[0]
                    if "&id=" in post_url:
                        expected_profile_id = post_url.split("&id=")[1].split("&")[0]
                    elif "id=" in post_url:
                        expected_profile_id = post_url.split("id=")[1].split("&")[0]
                    if "/posts/" in post_url:
                        parts = post_url.split("/posts/")
                        expected_post_id = parts[1].split("/")[0].split("?")[0]
                        if "/" in parts[0]:
                            profile_part = parts[0].split("/")[-1]
                            if profile_part.isdigit():
                                expected_profile_id = profile_part

                # Verify current URL matches expected identifiers
                if expected_story_fbid:
                    if expected_story_fbid not in current_url:
                        self.log(f"   ❌ Story fbid mismatch!")
                        self.log(f"      Expected: {expected_story_fbid}")
                        self.log(f"      Current: {current_url}")
                        return False, f"Facebook redirected to wrong post"
                
                if expected_post_id:
                    if expected_post_id not in current_url:
                        self.log(f"   ❌ Post ID mismatch!")
                        self.log(f"      Expected: {expected_post_id}")
                        self.log(f"      Current: {current_url}")
                        return False, f"Facebook redirected to wrong post"
                
                if expected_profile_id:
                    if expected_profile_id not in current_url:
                        self.log(f"   ⚠️  Profile ID may not match")
                        self.log(f"      Expected: {expected_profile_id}")
                        self.log(f"      Current: {current_url}")
                        # Don't fail here - just warn
                
            except Exception as e:
                self.log(f"Could not navigate for reaction: {e}")
                return False, f"Navigation failed: {e}"

        # Scroll post into view — scroll past media/video to reach action buttons
        self.log("Scrolling to reveal reaction buttons...")
        try:
            await self.page.evaluate("""() => {
                const a = document.querySelector('[role="article"]');
                if (a) {
                    a.scrollIntoView({block: 'center'});
                    window.scrollBy(0, 300);
                } else {
                    window.scrollBy(0, 1000);
                }
            }""")
            await asyncio.sleep(1.5)
        except Exception:
            pass

        await self._debug_dump("reaction_before_like")
        self.log("Looking for Like button...")
        try:
            # Tag the post's reaction action with a temp ID so we can use
            # Playwright locators.  Facebook now commonly labels the neutral
            # action "React" and also exposes separate "Like" reaction-count
            # buttons.  Selecting the first element containing "Like" can
            # therefore target the counter instead of the action.
            # Poll for up to ~10s — the post may still be hydrating after a slow load.
            found = None
            like_deadline = time.monotonic() + 10
            while time.monotonic() < like_deadline:
                found = await self.page.evaluate("""() => {
                    // Resolve the opened post container before looking for an
                    // action. Share URLs often render a post dialog over Home.
                    const visibleDialogs = [...document.querySelectorAll('[role="dialog"]')]
                        .filter(d => {
                            const r = d.getBoundingClientRect();
                            return r.width > 300 && r.height > 200;
                        })
                        .sort((a, b) => {
                            const ar = a.getBoundingClientRect();
                            const br = b.getBoundingClientRect();
                            return (ar.width * ar.height) - (br.width * br.height);
                        });
                    // A live or video permalink has no post dialog and no
                    // [role="article"] at all, and its [role="main"] wraps only
                    // the player - the action bar sits outside it. So the page
                    // itself is the container there. That is safe because this
                    // is a permalink, not the Home feed: there is no other
                    // post to react to by mistake, and the per-comment icons
                    // are excluded by size below.
                    const isVideoPage = /\\/(videos|watch|live)\\//.test(location.pathname)
                        || /^\\/watch\\/?$/.test(location.pathname)
                        || /\\/reel\\//.test(location.pathname);
                    // A container only counts as the post if it actually holds
                    // a post-sized reaction control. [role="article"] used to be
                    // taken on faith, and on a live page the FIRST article is a
                    // comment or a "More like this" card - a DIV with 4 buttons
                    // and no reaction at all, so the search found nothing.
                    const hasPostAction = el => {
                        if (!el) return false;
                        for (const b of el.querySelectorAll('[role="button"], button')) {
                            const ba = (b.getAttribute('aria-label') || '').toLowerCase();
                            const bt = (b.innerText || '').toLowerCase().trim();
                            const br = b.getBoundingClientRect();
                            if (br.width < 24 || br.height < 24) continue;
                            if (ba === 'react' || ba === 'like' ||
                                ba.startsWith('react with ') || bt === 'like') return true;
                        }
                        return false;
                    };
                    const rootCandidates = [
                        visibleDialogs.find(d => /'s post/i.test(d.innerText || '')),
                        ...document.querySelectorAll('[role="article"]'),
                        isVideoPage ? document.body : null,
                    ];
                    const root = rootCandidates.find(el => el && hasPostAction(el));
                    if (!root) return null;
                    root.id = '_fb_target_post_root';

                    // The post action row is above the comment-sort boundary.
                    // Any React/Like below "Most relevant" belongs to a comment.
                    const sortControls = [...root.querySelectorAll('[role="button"], button')]
                        .filter(el => {
                            const s = ((el.innerText || '') + ' ' +
                                (el.getAttribute('aria-label') || '')).toLowerCase();
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0 &&
                                (s.includes('most relevant') || s.includes('newest') ||
                                 s.includes('all comments'));
                        });
                    const commentBoundaryY = sortControls.length
                        ? Math.min(...sortControls.map(el => el.getBoundingClientRect().top))
                        : Infinity;

                    const all = [...root.querySelectorAll('[role="button"], button')];
                    const candidates = all.filter(el => {
                        const a = (el.getAttribute('aria-label') || '').toLowerCase();
                        const t = (el.innerText || '').toLowerCase().trim();
                        const r = el.getBoundingClientRect();
                        if (el.offsetParent === null || r.width <= 0 || r.height <= 0) return false;
                        if (r.top >= commentBoundaryY) return false;
                        // Comment reactions are tiny icons repeated on EVERY
                        // comment row: 'React' at 12x12 and, in a live video's
                        // chat list, 'Like' at 16x16 - one pair per comment.
                        // They are not the post action. Only 'react' used to be
                        // excluded, so on a live page the first comment's 16x16
                        // 'Like' scored the same 80 as the real 38x34 post
                        // button and won on DOM order.
                        const TINY_ICON_LABELS = ['react', 'like', 'love', 'care',
                                                  'haha', 'wow', 'sad', 'angry'];
                        if (TINY_ICON_LABELS.includes(a) && r.width < 24 && r.height < 24)
                            return false;
                        if (a.includes('people') || a.includes('like this') ||
                            a.includes('reaction;') || a.includes('reactions;')) return false;
                        // A numeric/text value on aria="Like" is normally the
                        // reaction summary/count, not the action button.
                        if (a === 'like' && t && t !== 'like') return false;
                        const reactionNames = ['like', 'love', 'care', 'haha', 'wow', 'sad', 'angry'];
                        const isSelectedReaction = reactionNames.some(name =>
                            a === name || a.startsWith(name + ' ') ||
                            (a.includes('remove') && a.includes(name)));
                        const isReactionAction = a === 'react' || a === 'like' ||
                            a.startsWith('react with ') || t === 'like' || isSelectedReaction;
                        return isReactionAction;
                    });
                    const score = el => {
                        const a = (el.getAttribute('aria-label') || '').toLowerCase();
                        const t = (el.innerText || '').toLowerCase().trim();
                        let points = 0;
                        if (a === 'react') points = 100;
                        else if (a.startsWith('react with ')) points = 90;
                        else if (a === 'like' && !t) points = 80;
                        else if (t === 'like') points = 70;
                        const dialog = el.closest('[role="dialog"]');
                        if (dialog) {
                            const dr = dialog.getBoundingClientRect();
                            if (dr.width > 0 && dr.height > 0) points += 1000;
                        }
                        if (el.closest('[role="article"]')) points += 300;
                        return points;
                    };
                    // Equal scores used to fall back to DOM order, which puts a
                    // comment row above the post's own action bar. Prominence
                    // breaks the tie instead: the post button is the big one.
                    candidates.sort((x, y) => {
                        const d = score(y) - score(x);
                        if (d) return d;
                        const rx = x.getBoundingClientRect();
                        const ry = y.getBoundingClientRect();
                        return (ry.width * ry.height) - (rx.width * rx.height);
                    });
                    const like = candidates[0];
                    if (!like) return null;
                    like.scrollIntoView({block: 'center'});
                    like.id = '_fb_like_btn';
                    return {
                        label: like.getAttribute('aria-label') || '',
                        text: (like.innerText || '').trim(),
                        pressed: like.getAttribute('aria-pressed') || ''
                    };
                }""")
                if found:
                    break
                await asyncio.sleep(1.5)

            if not found:
                self.log("Could not locate Like button")
                await self._dump_page_buttons("reaction_no_button")
                await self._debug_screenshot("reaction_no_button")
                return False, "Like button not found"

            like_label = found['label']
            self.log(f"Found '{like_label}'")
            # Preserve ANY existing reaction. Facebook may label the selected
            # action "Love", "Remove Love", or expose aria-pressed=true.
            existing_state = await self.page.evaluate("""() => {
                const el = document.getElementById('_fb_like_btn');
                if (!el) return null;
                const a = (el.getAttribute('aria-label') || '').toLowerCase();
                const t = (el.innerText || '').toLowerCase().trim();
                const pressed = el.getAttribute('aria-pressed') === 'true';
                const names = ['like', 'love', 'care', 'haha', 'wow', 'sad', 'angry'];
                for (const name of names) {
                    // Unambiguous however it is labelled.
                    if (a.includes('remove') && a.includes(name)) return name;
                    if (pressed && (a.includes(name) || t === name)) return name;
                    // A bare label of a NON-default reaction is the one already
                    // selected. 'like' is excluded on purpose: an UNREACTED
                    // button is labelled exactly "Like", so treating that as an
                    // existing reaction reported every post as already liked and
                    // never clicked. Only the search step may read a bare "Like",
                    // and it reads it as the button to press.
                    if (name !== 'like' &&
                        (a === name || a.startsWith(name + ' ') || t === name))
                        return name;
                }
                if (a.includes('unlike')) return 'like';
                return null;
            }""")
            if existing_state:
                self.log(f"  ℹ️  Already reacted with '{existing_state}' - preserving it")
                return True, f"Already reacted with '{existing_state}' (kept existing reaction)"
             
            # Check if already reacted by looking at the Like button label
            # If it says "Remove Like" or similar, the user already reacted
            if "remove" in like_label.lower() or "unlike" in like_label.lower():
                self.log(f"  ℹ️  Already reacted to this post - keeping existing reaction")
                return True, "Already reacted (kept existing reaction)"
            
            # Extract post author from Like button label for logging
            # Format: "React with Like to [Author]'s post" or just "Like"
            if " to " in like_label and "'s post" in like_label:
                post_author = like_label.split(" to ")[1].split("'s post")[0].strip()
                self.log(f"  📝 Post author detected: {post_author}")
            else:
                self.log(f"  📝 Post format: Generic (no author in label)")
            
            like_locator = self.page.locator('#_fb_like_btn')

            async def _verify_reacted(react_label: str) -> bool:
                """Return True if the button now shows the reaction as applied.

                Reacted buttons expose an aria-label like 'Remove <Reaction> from ...'.
                """
                try:
                    state = await self.page.evaluate(f"""() => {{
                        const root = document.getElementById('_fb_target_post_root');
                        if (!root) return false;
                        const all = [...root.querySelectorAll('[role="button"]')];
                        for (const el of all) {{
                            const a = (el.getAttribute('aria-label') || '').toLowerCase();
                            const r = el.getBoundingClientRect();
                            if (r.height >= 24 && !a.includes('comment') &&
                                a.includes('remove') && a.includes('{react_label.lower()}')) {{
                                return true;
                            }}
                        }}
                        return false;
                    }}""")
                    return bool(state)
                except Exception:
                    return False

            async def _is_share_dialog_open() -> bool:
                """Return True if a Share sheet dialog is open.

                A misclick on the 'Send this to friends or post it on your
                profile.' button (which overlaps the Love emoji in some flyout
                layouts) opens a sheet whose title is 'Share'. Retrying while
                that modal is up is pointless, so detect it and close it.
                """
                try:
                    return bool(await self.page.evaluate("""() => {
                        const visible = [...document.querySelectorAll('[role="dialog"]')]
                            .filter(d => d.offsetParent !== null && d.getBoundingClientRect().width > 0);
                        for (const d of visible) {
                            const t = (d.innerText || '').trim();
                            const a = (d.getAttribute('aria-label') || '').toLowerCase();
                            const first = t.split('\\n')[0].trim().toLowerCase();
                            if (a.includes('share') || first === 'share' || /say something about this/i.test(t)) {
                                return true;
                            }
                        }
                        return false;
                    }"""))
                except Exception:
                    return False

            if reaction == "like":
                await like_locator.click(timeout=5000)
                await asyncio.sleep(random.uniform(2, 3))
                if await _verify_reacted("like"):
                    self.log("Liked the post")
                    return True, "Liked the post"
                self.log("  ⚠️  Like clicked but not confirmed, retrying once...")
                try:
                    await like_locator.click(timeout=5000, force=True)
                    await asyncio.sleep(random.uniform(2, 3))
                except Exception:
                    pass
                if await _verify_reacted("like"):
                    self.log("Liked the post (retry)")
                    return True, "Liked the post (retry)"
                return False, "Could not confirm Like reaction"

            label = self.REACTION_LABELS[reaction]
            # The 'See more on Facebook' login overlay can appear over the post
            # even when the URL looks fine — bail out before wasting retries.
            if await self._login_overlay_present():
                self.log("Not logged in (login overlay detected)")
                return False, "Not logged in (login overlay)"
            self.log(f"Opening reaction picker for '{reaction}'...")
            
            # Check if user already has this specific reaction selected
            # Facebook shows selected reaction with "Remove" in the label
            already_selected = await self.page.evaluate(f"""() => {{
                const root = document.getElementById('_fb_target_post_root');
                if (!root) return false;
                const allButtons = [...root.querySelectorAll('[role="button"], button')];
                const selectedReaction = allButtons.find(btn => {{
                    const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                    const r = btn.getBoundingClientRect();
                    return r.height >= 24 && !label.includes('comment') &&
                        label.includes('remove') && label.includes('{reaction}');
                }});
                return selectedReaction !== null && selectedReaction !== undefined;
            }}""")
            
            if already_selected:
                self.log(f"  ℹ️  Already reacted with '{reaction}' - keeping existing reaction")
                return True, f"Already reacted with '{reaction}' (kept existing reaction)"

            # JS helper to scan for the reaction emoji in the picker
            _find_emoji_js = f"""(label) => {{
                const target = label.toLowerCase();
                const visible = (e) => {{
                    const r = e.getBoundingClientRect();
                    return e.offsetParent !== null && r.width > 0 && r.height > 0;
                }};
                const score = (e) => {{
                    const a = (e.getAttribute('aria-label') || '').toLowerCase();
                    const alt = (e.getAttribute('alt') || '').toLowerCase();
                    const t = (e.innerText || '').toLowerCase().trim();
                    const title = (e.getAttribute('title') || '').toLowerCase();
                    if (a !== target && alt !== target && t !== target && title !== target) return 0;
                    let pts = 1;
                    if (e.getAttribute('role') === 'button') pts += 10;
                    if (a === target) pts += 5;
                    if (e.tagName === 'IMG') pts += 3;
                    return pts;
                }};
                const all = [...document.querySelectorAll('[role="button"], button, img, span, a, div')];
                let best = null, bestPts = 0;
                for (const e of all) {{
                    if (!visible(e)) continue;
                    const pts = score(e);
                    if (pts > bestPts) {{ bestPts = pts; best = e; }}
                }}
                if (!best) return null;
                best.id = '_fb_reaction_btn';
                const r = best.getBoundingClientRect();
                return {{ x: r.x + r.width / 2, y: r.y + r.height / 2 }};
            }}"""

            async def _open_reaction_picker(retry: bool = False) -> bool:
                """Try to open the reaction picker and click the emoji.
                
                Uses four strategies:
                1. force=True hover (bypasses pointer-interception checks)
                2. JS-dispatched mouseenter/mouseover (bypasses overlay elements)
                3. Direct coordinate hover via page.mouse
                4. Press-and-hold on the Like button (media viewer / lightbox pattern)
                """
                # Strategy 1: force hover via Playwright
                try:
                    await like_locator.hover(timeout=5000, force=True)
                    await asyncio.sleep(2.0)
                except Exception:
                    pass

                # Check if picker appeared
                emoji = await self.page.evaluate(_find_emoji_js, label)
                if emoji:
                    return True

                # Strategy 2: dispatch mouse events via JS (bypasses sticky header overlays)
                try:
                    await self.page.evaluate("""() => {
                        const btn = document.getElementById('_fb_like_btn');
                        if (!btn) return;
                        const rect = btn.getBoundingClientRect();
                        const cx = rect.x + rect.width / 2;
                        const cy = rect.y + rect.height / 2;
                        const opts = {bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0};
                        btn.dispatchEvent(new PointerEvent('pointerenter', opts));
                        btn.dispatchEvent(new MouseEvent('mouseenter', opts));
                        btn.dispatchEvent(new PointerEvent('pointerover', opts));
                        btn.dispatchEvent(new MouseEvent('mouseover', opts));
                        btn.dispatchEvent(new MouseEvent('mousemove', opts));
                    }""")
                    wait = 3.5 if retry else 2.5
                    await asyncio.sleep(wait)
                except Exception:
                    pass

                emoji = await self.page.evaluate(_find_emoji_js, label)
                if emoji:
                    return True

                # Strategy 3: move mouse to button coordinates directly
                try:
                    coords = await self.page.evaluate("""() => {
                        const btn = document.getElementById('_fb_like_btn');
                        if (!btn) return null;
                        const r = btn.getBoundingClientRect();
                        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                    }""")
                    if coords:
                        await self.page.mouse.move(coords['x'], coords['y'])
                        await asyncio.sleep(2.5)
                except Exception:
                    pass

                emoji = await self.page.evaluate(_find_emoji_js, label)
                if emoji:
                    return True

                # Strategy 4: press-and-hold on the Like button.
                # On media viewer (lightbox) pages, hovering does NOT reveal the
                # reaction flyout — a press-and-hold (long-press) is required.
                self.log("  ⏳ Press-and-hold on Like button (media viewer pattern)...")
                try:
                    coords = await self.page.evaluate("""() => {
                        const btn = document.getElementById('_fb_like_btn');
                        if (!btn) return null;
                        btn.scrollIntoView({block: 'center'});
                        const r = btn.getBoundingClientRect();
                        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                    }""")
                    if coords:
                        await self.page.mouse.move(coords['x'], coords['y'])
                        await asyncio.sleep(0.5)
                        await self.page.mouse.down()
                        await asyncio.sleep(0.9)
                        await self.page.mouse.up()
                        await asyncio.sleep(1.0)
                except Exception:
                    pass

                emoji = await self.page.evaluate(_find_emoji_js, label)
                if emoji:
                    return True

                # After the press-and-hold, the flyout stays open while the
                # pointer remains over the Like button — nudge the pointer once
                # more (tiny move) to keep it anchored before giving up.
                try:
                    coords = await self.page.evaluate("""() => {
                        const btn = document.getElementById('_fb_like_btn');
                        if (!btn) return null;
                        const r = btn.getBoundingClientRect();
                        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                    }""")
                    if coords:
                        await self.page.mouse.move(coords['x'] + 2, coords['y'] + 2)
                        await asyncio.sleep(0.8)
                except Exception:
                    pass

                emoji = await self.page.evaluate(_find_emoji_js, label)
                return emoji is not None

            async def _click_emoji_trusted() -> bool:
                """Apply the reaction with trusted events, no drag.

                The picker and emoji are found correctly, but any mouse MOVEMENT
                between press and release is treated as a drag (drag-select /
                carousel swipe) which navigates into the Marketplace viewer.
                So: click in place — no movement between down and up.
                Strategy A: hover to grow the emoji, then press at a point
                            re-measured AFTER the animation settles.
                Strategy B: Playwright locator click (trusted pointer events).
                Strategy C: mouse down/up at the current center.
                Strategy D: JS-dispatched events (last resort).
                """
                async def _center(tag: str) -> dict | None:
                    return await self.page.evaluate(f"""() => {{
                        const el = document.getElementById('{tag}');
                        if (!el) return null;
                        const r = el.getBoundingClientRect();
                        return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
                    }}""")

                # Capture the picker/emoji state right before the click
                await self._debug_dom_dump(f"reaction_press_pre_attempt{attempt}", react_label=label)
                self.log(f"  🎯 Clicking '{label}'...")

                # Strategy A: trusted-click the emoji at a point whose TOPMOST
                # element is the emoji itself. Facebook grows the emoji AND the
                # Send button on hover, and React re-renders the picker (killing
                # any temp id), so we never trust a pre-hover point: we hover a
                # clear point on the emoji first, let the animation settle, then
                # re-locate the emoji FRESH by aria-label and re-scan its CURRENT
                # box. Only the topmost element matters — it receives the click —
                # so overlays lower in the stack cannot intercept the press.
                async def _scan() -> dict | None:
                    """Re-locate the emoji by aria-label and return a point on
                    its CURRENT box whose topmost element is the emoji."""
                    return await self.page.evaluate(f"""() => {{
                        const target = '{label}'.toLowerCase();
                        const all = [...document.querySelectorAll(
                            '[role="button"], button, [aria-label], img, span, a, div')];
                        let el = null, bestPts = 0;
                        for (const e of all) {{
                            const r = e.getBoundingClientRect();
                            if (r.width <= 0 || r.height <= 0) continue;
                            const a = ((e.getAttribute && (e.getAttribute('aria-label') || e.getAttribute('alt') || '')) || '').toLowerCase();
                            if (a !== target) continue;
                            let pts = 1;
                            if (e.getAttribute && e.getAttribute('role') === 'button') pts += 10;
                            if (e.getAttribute && e.getAttribute('aria-label')) pts += 5;
                            if (e.tagName === 'IMG') pts += 3;
                            if (pts > bestPts) {{ bestPts = pts; el = e; }}
                        }}
                        if (!el) return null;
                        try {{ el.id = '_fb_reaction_btn'; }} catch (e) {{}}
                        const r = el.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) return null;
                        const onEmoji = (node) => node === el || el.contains(node) ||
                            (node.contains && node.contains(el));
                        const safe = (x, y) => {{
                            let stack = [];
                            try {{ stack = document.elementsFromPoint(x, y); }} catch (e) {{ return false; }}
                            if (!stack.length) return false;
                            return onEmoji(stack[0]);
                        }};
                        const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
                        if (safe(cx, cy)) return {{x: cx, y: cy}};
                        const step = 10;
                        let best = null, bestEdge = -1;
                        for (let gy = 0; gy < step; gy++) {{
                            for (let gx = 0; gx < step; gx++) {{
                                const x = r.x + (r.width * (gx + 0.5)) / step;
                                const y = r.y + (r.height * (gy + 0.5)) / step;
                                if (!safe(x, y)) continue;
                                const edge = Math.min(x - r.x, r.x + r.width - x, y - r.y, r.y + r.height - y);
                                if (edge > bestEdge) {{ bestEdge = edge; best = {{x, y}}; }}
                            }}
                        }}
                        return best;
                    }}""")

                async def _verify(pt: dict) -> bool:
                    """True if the topmost element at pt is the emoji.

                    Also logs the top-3 hit-test stack at pt (what is actually
                    under the cursor) so overlap problems are easy to diagnose.
                    """
                    try:
                        res = await self.page.evaluate(f"""(pt) => {{
                            const target = '{label}'.toLowerCase();
                            const el = [...document.querySelectorAll('[role="button"], button, [aria-label]')]
                                .find(e => {{
                                    const r = e.getBoundingClientRect();
                                    return r.width > 0 && r.height > 0 &&
                                        (e.getAttribute('aria-label') || '').toLowerCase() === target;
                                }});
                            if (!el) return {{ok: false, stack: []}};
                            let stack = [];
                            try {{ stack = document.elementsFromPoint(pt.x, pt.y); }} catch (e) {{ return {{ok: false, stack: []}}; }}
                            if (!stack.length) return {{ok: false, stack: []}};
                            const top = stack[0];
                            const ok = top === el || el.contains(top) || (top.contains && top.contains(el));
                            const brief = stack.slice(0, 3).map(e => {{
                                const r2 = e.getBoundingClientRect();
                                const a = (e.getAttribute && (e.getAttribute('aria-label') || e.getAttribute('alt') || '')) || '';
                                return (e.tagName || '?').toLowerCase() + '[' + a.slice(0, 30) + ']@' +
                                    Math.round(r2.x) + ',' + Math.round(r2.y);
                            }});
                            return {{ok: ok, stack: brief}};
                        }}""", pt)
                        if res and res.get("stack"):
                            self.log(f"    🔍 hit-test @ ({pt['x']:.0f},{pt['y']:.0f}) top-3: "
                                     + " | ".join(res.get("stack", [])))
                        return bool(res.get("ok"))
                    except Exception:
                        return False

                async def _press_clear_point(when: str) -> bool:
                    """Hover a clear point on the emoji (triggers its growth
                    animation), wait for it to settle, re-scan the CURRENT box,
                    move, verify, and press in place. True only if a verified
                    press happened."""
                    try:
                        # 1) Hover a clear point so the EMOJI gets the hover
                        #    (not the Send overlay) and its growth animation runs.
                        pt = await _scan()
                        if not pt:
                            return False
                        await self.page.mouse.move(pt['x'], pt['y'])
                        await asyncio.sleep(0.8)

                        # 2) Re-scan the CURRENT (grown) box and move there.
                        pt = await _scan()
                        if not pt:
                            return False
                        await self.page.mouse.move(pt['x'], pt['y'])
                        await asyncio.sleep(0.4)

                        # 3) Final verification, then press in place (no drag).
                        if not await _verify(pt):
                            self.log(f"  ⚠️  {when}: point covered at press time — skipping")
                            return False
                        await self.page.mouse.down()
                        await asyncio.sleep(0.35)
                        await self.page.mouse.up()
                        self.log(f"  ✅ Clicked emoji at clear point ({when})")
                        return True
                    except Exception:
                        try:
                            await self.page.mouse.up()
                        except Exception:
                            pass
                        return False

                # Strategy A main: hover -> press at a fresh clear point.
                for press_attempt in range(3):
                    if await _press_clear_point(f"scan {press_attempt + 1}"):
                        return True
                # Last-ditch: right edge, re-measured live after hover settle,
                # verified before pressing.
                try:
                    pt = await self.page.evaluate(f"""() => {{
                        const target = '{label}'.toLowerCase();
                        const el = [...document.querySelectorAll('[role="button"], button, [aria-label]')]
                            .find(e => {{
                                const r = e.getBoundingClientRect();
                                return r.width > 0 && r.height > 0 &&
                                    (e.getAttribute('aria-label') || '').toLowerCase() === target;
                            }});
                        if (!el) return null;
                        const r = el.getBoundingClientRect();
                        return {{x: r.x + r.width - 4, y: r.y + r.height / 2}};
                    }}""")
                    if pt:
                        await self.page.mouse.move(pt['x'], pt['y'])
                        await asyncio.sleep(0.8)
                        if await _verify(pt):
                            await self.page.mouse.down()
                            await asyncio.sleep(0.35)
                            await self.page.mouse.up()
                            self.log("  ✅ Clicked emoji at right edge (last-ditch)")
                            return True
                except Exception:
                    try:
                        await self.page.mouse.up()
                    except Exception:
                        pass

                # Strategy B: trusted locator click on the exact aria-label button.
                # Playwright's click emits TRUSTED pointer events, which Facebook
                # accepts for reactions (unlike JS-dispatched events).
                try:
                    emoji_btn = self.page.locator(f'[role="button"][aria-label="{label}"]').last
                    await emoji_btn.click(timeout=4000, force=True, no_wait_after=True)
                    self.log("  ✅ Clicked via locator")
                    return True
                except Exception:
                    pass

                # Strategy C: mouse down/up at the emoji's current center (no drag)
                coords = await _center('_fb_reaction_btn')
                if not coords:
                    return False
                await self.page.mouse.move(coords['x'], coords['y'])
                await asyncio.sleep(0.8)
                coords = await _center('_fb_reaction_btn')
                if coords:
                    await self.page.mouse.move(coords['x'], coords['y'])
                    await asyncio.sleep(0.3)
                await self.page.mouse.down()
                await asyncio.sleep(0.3)
                await self.page.mouse.up()
                self.log("  ✅ Clicked via mouse")
                return True

                # Strategy D: JS-dispatched click directly on the emoji element.
                # LAST RESORT — synthetic events are untrusted and Facebook
                # usually ignores them for reactions, but try anyway.
                js_clicked = await self.page.evaluate(f"""() => {{
                    const el = document.getElementById('_fb_reaction_btn');
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const x = r.x + r.width / 2, y = r.y + r.height / 2;
                    const base = {{bubbles: true, cancelable: true, view: window,
                                   clientX: x, clientY: y, button: 0, detail: 1}};
                    el.dispatchEvent(new PointerEvent('pointerdown',
                        {{...base, pointerId: 1, pointerType: 'mouse', isPrimary: true}}));
                    el.dispatchEvent(new MouseEvent('mousedown', base));
                    el.dispatchEvent(new PointerEvent('pointerup',
                        {{...base, pointerId: 1, pointerType: 'mouse', isPrimary: true}}));
                    el.dispatchEvent(new MouseEvent('mouseup', base));
                    el.dispatchEvent(new MouseEvent('click', base));
                    return true;
                }}""")
                if js_clicked:
                    self.log("  ✅ Clicked via JS dispatch")
                    return True

                return False

            # Attempt up to 3 times to open the picker, click the emoji, and confirm
            for attempt in range(1, 4):
                found = await _open_reaction_picker(retry=(attempt > 1))
                if not found:
                    if attempt < 3:
                        self.log(f"Picker not found (attempt {attempt}/3), retrying hover...")
                        continue
                    break
                self.log(f"Found '{label}' reaction, clicking...")
                clicked = await _click_emoji_trusted()
                if not clicked:
                    self.log(f"  ⚠️  Click failed (attempt {attempt}/3), retrying...")
                    continue
                await asyncio.sleep(random.uniform(1.5, 2.5))
                if await _verify_reacted(label):
                    self.log(f"Reacted with '{label}'")
                    return True, f"Reacted with '{label}'"
                self.log(f"  ⚠️  Click registered but reaction not confirmed (attempt {attempt}/3), retrying...")
                await self._debug_dump(f"reaction_failed_attempt{attempt}")
                try:
                    like_label = await self.page.get_attribute('#_fb_like_btn', 'aria-label')
                    self.log(f"  📋 Like button label: {like_label}")
                except Exception:
                    pass
                try:
                    cur = self.page.url
                    self.log(f"  📋 URL after attempt: {cur}")
                    if "commerce/" in cur or "/marketplace/" in cur or "listing/" in cur:
                        self.log("  ⚠️  NAVIGATED AWAY from the post into a Marketplace listing viewer!")
                except Exception:
                    pass
                await self._debug_dom_dump(f"reaction_failed_attempt{attempt}", react_label=label)
                if await _is_share_dialog_open():
                    self.log("  ⚠️  A Share dialog opened from the misclick — closing it before retry")
                    try:
                        await self.page.keyboard.press("Escape")
                    except Exception:
                        pass
                    await asyncio.sleep(0.8)
                if attempt == 3:
                    await self._debug_screenshot(f"reaction_failed_attempt{attempt}", react_label=label)

            # Never substitute a plain Like for another requested reaction.
            if await self._login_overlay_present():
                self.log("Not logged in (login overlay detected)")
                return False, "Not logged in (login overlay)"
            self.log(f"Could not confirm '{reaction}' on the target post; no fallback Like was sent")
            await self._debug_screenshot("reaction_fallback_failed", react_label=label)
            return False, f"Could not apply '{reaction}' reaction to the target post"

        except Exception as e:
            self.log(f"Could not react: {e}")
            await self._dump_page_buttons("reaction_error")
            return False, f"Reaction error: {e}"

    # ── Auto Comment ──────────────────────────────────────

    async def _auto_comment(self, post_url: str | None, comment_text: str | None) -> bool:
        """Post a comment on the post.
        
        If comment_text contains multiple lines, one will be selected randomly.
        Uses JavaScript to find the comment box, then Playwright's keyboard
        for reliable React-compatible text input and submission.
        """
        self.last_comment_error = ""
        if not comment_text or not comment_text.strip():
            return True

        # Facebook does NOT render the comment composer when the post's page
        # resources are blocked — verified by comparing a real browser (box
        # present) with the automation's resource-blocked page (box absent).
        # Load the comment page fully so the composer renders.
        self._block_resources = False
        self.log("Full page load enabled for comment (resource blocking off)")

        # Get delay settings to avoid spam detection
        delays = cfg.get_comment_delays()
        
        # Handle multiple comments (one per line) - select one randomly
        comment_lines = [line.strip() for line in comment_text.strip().splitlines() if line.strip()]
        if not comment_lines:
            return True
        
        # Select one comment randomly from the list
        selected_comment = random.choice(comment_lines)
        self.log(f"Selected comment ({len(comment_lines)} available): '{selected_comment[:50]}...'")
        comment_text = selected_comment

        if post_url:
            self.log(f"Navigating to post for comment...")
            try:
                nav_error = None
                for nav_attempt in range(1, 4):
                    try:
                        await self.page.goto(
                            post_url, timeout=30000,
                            wait_until="domcontentloaded")
                        nav_error = None
                        break
                    except Exception as e:
                        nav_error = e
                        if nav_attempt < 3:
                            self.log(
                                f"Comment navigation attempt {nav_attempt}/3 failed; retrying...")
                            await asyncio.sleep(3)
                if nav_error is not None:
                    raise nav_error
                # Add delay after navigation
                delay_after_nav = random.uniform(
                    delays["after_navigation_min"], 
                    delays["after_navigation_max"]
                )
                self.log(f"Waiting {delay_after_nav:.1f}s after navigation...")
                await asyncio.sleep(delay_after_nav)
                current_url = self.page.url
                self.log(f"Comment page URL: {current_url}")
                status = None
                if not await self._is_logged_in(timeout=3):
                    # Ask the classifier before giving up: a 3 s look at a
                    # half-loaded post page is not evidence of a dead session.
                    status = await self._classify_account_access()
                    if status == self.LOGGED_IN:
                        self.log("Session is live - the post page was just slow")
                        status = None
                if status is not None:
                    self.last_comment_error = status.replace('_', ' ')
                    self.log(f"Cannot comment — account status: {self.last_comment_error}")
                    return False

                # A /share/p/ link opens the post as a MODAL over the home
                # feed, and that modal's comment composer frequently never
                # renders under headless. The canonical permalink renders the
                # composer as first-class page layout, so prefer it: read the
                # canonical / og:url and navigate there as a full page.
                try:
                    canonical = await self.page.evaluate("""() => {
                        const c = document.querySelector('link[rel="canonical"]');
                        if (c && c.href && /facebook\\.com/.test(c.href)) return c.href;
                        const og = document.querySelector('meta[property="og:url"]');
                        if (og && og.content && /facebook\\.com/.test(og.content)) return og.content;
                        return null;
                    }""")
                    cur = self.page.url
                    if (canonical and canonical != cur
                            and "/share/" in cur
                            and "/share/" not in canonical):
                        self.log(f"Opening canonical permalink for a reliable "
                                 f"composer: {canonical}")
                        await self.page.goto(canonical, timeout=30000,
                                             wait_until="domcontentloaded")
                        await asyncio.sleep(random.uniform(
                            delays["after_navigation_min"],
                            delays["after_navigation_max"]))
                except Exception as e:
                    self.log(f"Canonical permalink lookup skipped: {e}")
                # A /share/ redirect can land on the permalink WITH a
                # "share_url" query parameter. In that state Facebook renders
                # a "View shared post" interstitial where the composer is
                # hidden (and a bogus 'commenting has been turned off' notice
                # can appear even though the post allows comments). Load the
                # clean permalink (param removed) so the composer renders.
                try:
                    cur = self.page.url or ""
                    if "share_url=" in cur:
                        clean = cur.split("&share_url=")[0].split("?share_url=")[0]
                        if clean and clean != cur:
                            self.log(f"Opening clean permalink (removed share "
                                     f"interstitial): {clean}")
                            await self.page.goto(clean, timeout=30000,
                                                 wait_until="domcontentloaded")
                            await asyncio.sleep(random.uniform(
                                delays["after_navigation_min"],
                                delays["after_navigation_max"]))
                except Exception as e:
                    self.log(f"Share URL cleanup skipped: {e}")
            except Exception as e:
                self.last_comment_error = f"navigation failed after retries: {e}"
                self.log(f"Could not navigate for comment: {e}")
                return False

        # Bring the post into view (window scroll — harmless on both the
        # permalink page and the modal; modal-specific loading is handled
        # in the wait loop below).
        try:
            await self.page.evaluate("""() => {
                const a = document.querySelector("[role='article']");
                if (a) { a.scrollIntoView({block: 'center'}); }
            }""")
            await asyncio.sleep(1)
        except Exception:
            pass

        await self._debug_dump("comment_before_box")
        self.log("Looking for comment box...")
        try:
            # Tag the actual opened post. Never let a global selector fall back
            # to a random comment/editor in the Home feed.
            target_kind = await self.page.evaluate("""() => {
                const isReel = /\\/reel\\//.test(location.href);
                // A live or video permalink is neither a dialog nor an
                // article: it renders Overview / Live chat / Your replies
                // under [role="main"], with no [role="article"] anywhere and
                // its only dialog a 329x47 "Close reactions" strip. Without
                // this branch it matched nothing and was reported as the Home
                // feed, so a live link could never even reach the composer
                // search - or the diagnosis that says comments are off.
                const isVideo = /\\/(videos|watch|live)\\//.test(location.pathname)
                    || /^\\/watch\\/?$/.test(location.pathname);
                const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                    .filter(d => {
                        const r = d.getBoundingClientRect();
                        if (r.width <= 300 || r.height <= 200) return false;
                        const txt = (d.innerText || '').toLowerCase();
                        if (txt.includes("'s post")) return true;
                        if (d.querySelector('video, [aria-label*="reel" i]')) return true;
                        return false;
                    })
                    .sort((a, b) => {
                        const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
                        return (ar.width * ar.height) - (br.width * br.height);
                    });
                let root = dialogs[0] || document.querySelector('[role="article"]');
                if (!root && (isReel || isVideo)) {
                    const video = document.querySelector('video');
                    const videoHost = video && video.closest('[role="dialog"]');
                    // A bare <a aria-label="Reels"> in the nav is not the
                    // post: on a live page that anchor is the first match and
                    // is empty, so require a box big enough to hold a player
                    // before trusting the label, and only on a reel URL.
                    const reelHost = isReel
                        ? [...document.querySelectorAll('[aria-label*="Reel" i]')]
                              .find(e => {
                                  const r = e.getBoundingClientRect();
                                  return r.width > 200 && r.height > 200;
                              })
                        : null;
                    root = videoHost || reelHost
                        || document.querySelector('[role="main"]')
                        || document.body;
                }
                if (!root) return '';
                root.id = '_fb_comment_target_root';
                return dialogs.length ? 'dialog'
                    : (document.querySelector('[role="article"]') ? 'article' : 'page');
            }""")
            if not target_kind:
                # Only the home page is the home page. This used to report
                # "Facebook returned Home/feed" for any layout it did not
                # recognise, so a run that landed on exactly the right post
                # was blamed on a redirect that never happened.
                try:
                    landed = self.page.url
                except Exception:
                    landed = ""
                if self._is_home_url(landed):
                    self.last_comment_error = "target post did not open"
                    self.log("Target post did not open (Facebook returned Home/feed)")
                else:
                    self.last_comment_error = "post layout not recognised"
                    self.log(f"Post opened but no commentable root was found "
                             f"on {landed}")
                await self._debug_screenshot("comment_target_not_open")
                return False
            # A modal (dialog) sits OVER the home feed, so we must never search
            # the page at large or we could comment on a background feed post.
            # A permalink page (article) has no such feed, so a page-scope
            # fallback there is safe.
            is_modal = target_kind == "dialog"
            target_root = self.page.locator('#_fb_comment_target_root')

            # The post footer (action bar + comment composer) often renders a
            # moment after the post body — the initial navigation returns on
            # "domcontentloaded", before the footer's data fetch completes.
            # Poll for the composer/action bar to appear, treating a visible
            # loading spinner as "keep waiting". We scroll only gently (one
            # viewport) to nudge lazy content WITHOUT jamming to the bottom,
            # which would trigger runaway "load more comments" pagination.
            async def _wait_for_composer():
                self.log("Waiting for the comment area to load...")
                composer_ready = False
                for i in range(16):
                    try:
                        state = await self.page.evaluate("""() => {
                            const root = document.getElementById('_fb_comment_target_root');
                            if (!root) return 'gone';
                            const hasBox = !!root.querySelector(
                                '[contenteditable="true"][aria-label*="comment" i],' +
                                '[contenteditable="true"][aria-placeholder*="comment" i],' +
                                'div[role="textbox"][contenteditable="true"],' +
                                'textarea:not([aria-hidden="true"]),' +
                                '[aria-label*="Leave a comment" i],' +
                                '[aria-label="Comment"][role="button"]');
                            if (hasBox) return 'ready';
                            // Still loading? a spinner/busy region means "wait".
                            const busy = root.querySelector(
                                '[role="progressbar"], [aria-busy="true"]');
                            return busy ? 'loading' : 'absent';
                        }""")
                        if state == "ready":
                            composer_ready = True
                            break
                        # Gentle nudge every other tick (one viewport, not to end)
                        if i % 2 == 1:
                            await self.page.evaluate(
                                "() => window.scrollBy(0, window.innerHeight * 0.6)")
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                if composer_ready:
                    self.log("Comment area loaded.")
                else:
                    self.log("Comment area did not appear after wait — trying anyway...")

            await _wait_for_composer()

            box_css = [
                '[contenteditable="true"][aria-label*="comment" i]',
                '[contenteditable="true"][aria-placeholder*="comment" i]',
                '[contenteditable="true"][data-lexical-editor="true"]',
                'div[role="textbox"][contenteditable="true"]:not([aria-hidden="true"])',
                'div[role="textbox"][aria-placeholder*="comment" i]',
                'textarea:not([aria-hidden="true"])',
                'div[contenteditable="true"]:not([aria-hidden="true"])',
            ]

            async def _find_box(scope):
                """Locate the comment editor within a given scope."""
                return await self._find(
                    css=box_css, role="textbox", timeout=5,
                    visible_only=True, use_last=True, parent=scope)

            async def _find_leave_btn(scope):
                return await self._find(
                    css=[
                        '[aria-label*="Leave a comment" i]',
                        '[aria-label*="Comment" i][role="button"]',
                        'div[role="button"]:has-text("Comment")',
                    ],
                    visible_only=True, timeout=5, parent=scope)

            # Search scoped to the tagged post first. On a permalink page
            # (not a modal) also allow a page-scope pass, because the composer
            # can render as a SIBLING of the post rather than a descendant.
            # For a modal we stay strictly inside the dialog — the home feed
            # behind it must never be a fallback target.
            scopes = (target_root,) if is_modal else (target_root, self.page)

            async def _locate_box() -> "object | None":
                for scope in scopes:
                    box = await _find_box(scope)
                    if box:
                        return box
                    leave_btn = await _find_leave_btn(scope)
                    if leave_btn:
                        self.log("Clicking 'Comment' to open the composer...")
                        try:
                            await leave_btn.scroll_into_view_if_needed()
                            await asyncio.sleep(0.5)
                            await leave_btn.click(force=True)
                            await asyncio.sleep(random.uniform(
                                delays["after_clicking_box_min"],
                                delays["after_clicking_box_max"]))
                        except Exception:
                            continue
                        # Re-find only within the SAME scope — never widen to
                        # the page for a modal (would risk the background feed).
                        box = await _find_box(scope)
                        if box:
                            return box
                return None

            comment_box = await _locate_box()

            if not comment_box:
                # Inspect what Facebook ACTUALLY served this account for this
                # post: which action-bar buttons exist (Like/Comment/Share),
                # whether a composer exists, and any gating text. This tells
                # us definitively whether the Comment affordance is missing
                # (a restriction we cannot code around) or present-but-unopened
                # (a session/timing issue that a real profile could fix).
                reason = "commenting unavailable for this account/post"
                diag = {}
                try:
                    diag = await self.page.evaluate("""() => {
                        const root = document.getElementById('_fb_comment_target_root')
                                     || document.body;
                        const q = sel => !!root.querySelector(sel);
                        const t = ((root && root.innerText) || '').toLowerCase();
                        const has = s => t.includes(s);
                        let html = '';
                        try { html = document.documentElement.outerHTML || ''; } catch (e) {}
                        const h = html.toLowerCase();
                        const hhas = s => h.includes(s);
                        const disabled_notice =
                            hhas('commenting has been turned off for this post') ||
                            hhas('comments have been turned off for this post') ||
                            hhas('commenting is turned off for this post') ||
                            hhas('commenting has been disabled for this post') ||
                            hhas('comments are turned off for this post') ||
                            hhas('comments are off for this post');
                        const viewer_cannot_comment =
                            hhas('"can_viewer_comment":false');
                        return {
                            like:  q('[aria-label="Like"][role="button"], [aria-label*="Like" i][role="button"]'),
                            comment: q('[aria-label="Comment"][role="button"], [aria-label*="Leave a comment" i]'),
                            share: q('[aria-label*="Share" i][role="button"]'),
                            composer: q('[contenteditable="true"], textarea:not([aria-hidden="true"]), div[role="textbox"]'),
                            disabled_notice: disabled_notice,
                            viewer_cannot_comment: viewer_cannot_comment,
                            gate: (has('log in to comment') || has('see more on facebook')) ? 'login'
                                : (has('who can comment') || has('turned off comment')
                                   || has('comments are limited') || has('limited who can comment')
                                   || has('turned off for this post')
                                   || has('this post') && has('comment') && has('friends')) ? 'restricted'
                                : '',
                        };
                    }""")
                    self.log(
                        f"Diagnosis — action bar: Like={'Y' if diag.get('like') else 'N'} "
                        f"Comment={'Y' if diag.get('comment') else 'N'} "
                        f"Share={'Y' if diag.get('share') else 'N'}; "
                        f"composer={'Y' if diag.get('composer') else 'N'}; "
                        f"gate={diag.get('gate') or 'none'}; "
                        f"comments_off={'Y' if diag.get('disabled_notice') else 'N'}; "
                        f"can_comment={'N' if diag.get('viewer_cannot_comment') else 'Y'}")
                except Exception:
                    pass

                # A 'comments off' notice can be the SHARE-page interstitial:
                # Facebook serves it on /share/ redirects even when the post
                # itself allows comments (can_viewer_comment is true). Retry
                # once on the clean permalink before giving up.
                if (diag.get("disabled_notice")
                        and not diag.get("viewer_cannot_comment")
                        and (self.page.url or "").startswith(
                            "https://www.facebook.com/permalink.php")
                        and "share_url=" in (self.page.url or "")):
                    clean = self.page.url.split("&share_url=")[0].split("?share_url=")[0]
                    self.log(f"Retrying on clean permalink (removed share "
                             f"interstitial): {clean}")
                    try:
                        await self.page.goto(clean, timeout=30000,
                                             wait_until="domcontentloaded")
                        await asyncio.sleep(random.uniform(
                            delays["after_navigation_min"],
                            delays["after_navigation_max"]))
                        # Re-tag the post on the freshly loaded page.
                        try:
                            kind = await self.page.evaluate("""() => {
                                const a = document.querySelector('[role="article"]');
                                const d = document.querySelector('[role="dialog"]');
                                const root = d || a;
                                if (root) root.id = '_fb_comment_target_root';
                                return d ? 'dialog' : (a ? 'article' : '');
                            }""")
                            if kind:
                                is_modal = kind == "dialog"
                                target_root = self.page.locator('#_fb_comment_target_root')
                                scopes = (target_root,) if is_modal else (target_root, self.page)
                        except Exception:
                            pass
                        await _wait_for_composer()
                        comment_box = await _locate_box()
                    except Exception as e:
                        self.log(f"Clean-permalink retry failed: {e}")

                if not comment_box:
                    if diag.get("viewer_cannot_comment"):
                        # Per VIEWER, not per post: the same live video returns
                        # can_viewer_comment=true for one profile and false for
                        # another at the same moment, because the author limited
                        # who may comment. So this is never a reason to skip the
                        # post for the rest of the queue.
                        reason = ("this account may not comment here "
                                  "(can_viewer_comment=false - the author "
                                  "limited who can comment; other accounts "
                                  "may still be allowed)")
                    elif diag.get("disabled_notice"):
                        reason = ("Facebook served a 'comments off' notice but "
                                  "says this account can comment — transient "
                                  "share-page state; retry did not help")
                    elif diag.get("gate") == "login":
                        reason = "logged out or session expired"
                    elif diag.get("gate") == "restricted":
                        reason = "commenting restricted on this post"
                    elif diag.get("share") and not diag.get("comment"):
                        # Like/Share offered but NO Comment button → Facebook is
                        # withholding the comment option for this account here.
                        reason = ("Facebook is not offering this account a Comment "
                                  "button on this post (comment restriction)")
                    elif diag.get("comment") and not diag.get("composer"):
                        reason = ("Comment button present but composer would not "
                                  "open (likely the injected-cookie session)")
                    self.last_comment_error = reason
                    self.log(f"Comment textbox not found — {reason}")
                    await self._dump_page_buttons("comment_failed")
                    await self._debug_screenshot("comment_failed")
                    return False

            # Click to focus the box, then type via keyboard (React-compatible)
            await comment_box.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await comment_box.click(force=True)
            await asyncio.sleep(random.uniform(0.7, 1.2))

            # Use keyboard.type() which produces real keystrokes that React detects
            await self.page.keyboard.type(comment_text, delay=random.randint(60, 150))
            await asyncio.sleep(random.uniform(0.5, 1.0))

            # Submit with Enter
            await self.page.keyboard.press("Enter")
            
            # Add delay after posting
            delay_after_post = random.uniform(
                delays["after_posting_min"], 
                delays["after_posting_max"]
            )
            self.log(f"Waiting {delay_after_post:.1f}s after posting comment...")
            await asyncio.sleep(delay_after_post)

            self.log(f"Comment posted: '{comment_text[:50]}...'")
            return True
        except Exception as e:
            self.last_comment_error = f"comment error: {e}"
            self.log(f"Could not post comment: {e}")
            await self._dump_page_buttons("comment_error")
            await self._debug_screenshot("comment_error")
            return False

    # ── Login check ────────────────────────────────────────

    async def _dismiss_account_chooser(self) -> bool:
        """Click past the "Continue as <name> / Use another profile" screen.

        Facebook shows this when a remembered profile's session has been
        invalidated server-side. The page carries the remembered name and a
        Continue button but NO email field, so a login run found no form and
        gave up with "Email input not found". "Use another profile" opens the
        ordinary email + password form this method's caller expects.
        """
        try:
            link = self.page.get_by_text("Use another profile", exact=True).first
            if await link.count() == 0:
                return False
            await link.click(timeout=8000)
            await asyncio.sleep(3)
            self.log("Account chooser dismissed - opened the login form")
            return True
        except Exception:
            return False

    async def _login_overlay_present(self) -> bool:
        """True when a Facebook login gate is on the page.

        See LOGIN_GATE_JS: the 'See more on Facebook' overlay, a visible
        login form, or the account chooser a server-invalidated session
        lands on.
        """
        try:
            return bool(await self.page.evaluate(LOGIN_GATE_JS))
        except Exception:
            return False

    @staticmethod
    def _is_home_url(url: str) -> bool:
        """True when `url` is the Facebook home page itself.

        Facebook sends a session that cannot use the account somewhere else
        (login, checkpoint, confirmemail.php, two-factor, recover), so landing
        on "/" after opening facebook.com is the one signal that the account
        can actually be used. The query string is ignored: "/?sk=welcome" and
        "/?_rdr" are still home.
        """
        try:
            parts = urllib.parse.urlsplit((url or "").lower())
        except Exception:
            return False
        host = parts.netloc.rsplit("@", 1)[-1].split(":", 1)[0]
        if host != "facebook.com" and not host.endswith(".facebook.com"):
            return False
        return parts.path.rstrip("/") in ("", "/home.php")

    # Path prefixes Facebook sends a session it will not let use the account:
    # a login form, a checkpoint, a two-factor prompt, an email confirmation
    # or an account-recovery flow.
    GATE_PATHS = ("/login", "/checkpoint", "/twofactor",
                  "/two_step_verification", "/approvals", "/confirmemail",
                  "/recover")

    @classmethod
    def _is_gated_url(cls, url: str) -> bool:
        """True when `url` is one of Facebook's account gates.

        The PATH decides, never a substring of the whole URL: an ordinary post
        in a group called "carrecovery" or a page named "DataRecovery" would
        otherwise read as a recovery gate, and the same for a "?next=...login"
        query on a perfectly normal page.
        """
        try:
            parts = urllib.parse.urlsplit((url or "").lower())
        except Exception:
            return False
        return parts.path.startswith(cls.GATE_PATHS)

    async def _is_logged_in(self, timeout: int = 10) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                page_url = self.page.url.lower()
            except Exception:
                await asyncio.sleep(0.3)
                continue

            if "facebook.com" not in page_url:
                await asyncio.sleep(0.5)
                continue

            on_login_page = self._is_gated_url(page_url)

            email_count = await self.page.locator('input[name="email"]').count()
            pass_count = await self.page.locator('input[name="pass"]').count()
            on_login_form = email_count > 0 or pass_count > 0

            # The 'See more on Facebook' overlay can appear over a post page
            # without any URL change — treat it as not logged in too.
            if on_login_page or on_login_form or await self._login_overlay_present():
                await asyncio.sleep(0.5)
                continue

            return True

        return False

    LOGGED_IN = "logged_in"

    async def _classify_account_access(self, page=None) -> str:
        """Why Facebook access is unavailable - or LOGGED_IN when it is not.

        The classifier used to have no way of saying "this account is fine".
        Every caller asked it only after something had already failed, so a
        live session that failed for another reason (a slow page, a post that
        would not load) came back as "unknown_not_logged_in" and the account
        was demoted on the sheet. Answering LOGGED_IN lets a caller tell a
        dead session from a working one.
        """
        target = page or self.page
        if not target:
            return "unknown"
        try:
            url = target.url.lower()
        except Exception:
            return "unknown"
        # A live session first: anything else here is a reason for failure,
        # and a working account must never be given one.
        try:
            if "facebook.com" in url and await self._is_logged_in(timeout=5):
                return self.LOGGED_IN
        except Exception:
            pass
        # Never navigated (about:blank) or navigated off Facebook: this says
        # nothing about the account, so it must not be recorded as one.
        if "facebook.com" not in url:
            return "unreachable"
        try:
            body = (await target.locator("body").inner_text(timeout=3000)).lower()
        except Exception:
            return "unknown"
        disabled_terms = (
            "account has been disabled", "account is disabled",
            "we suspended your account", "your account was suspended",
            "account suspended", "you cannot use facebook",
        )
        checkpoint_terms = (
            "confirm your identity", "security check", "checkpoint",
            "review requested", "request a review", "two-factor",
            "enter the code", "account restricted",
        )
        if any(term in body for term in disabled_terms):
            return "disabled_or_suspended"
        if "confirmemail" in url:
            return "email_confirmation_required"
        if any(term in url for term in ("checkpoint", "twofactor", "approvals")) \
                or any(term in body for term in checkpoint_terms):
            return "checkpoint_or_verification_required"
        if "login" in url or await target.locator(
                'input[name="email"], input[name="pass"]').count():
            return "logged_out_or_session_expired"
        # Evaluate the gate on the page being classified, not self.page: the
        # login scan passes its own persistent-context page, so checking
        # self.page here silently found nothing and every expired session was
        # reported as "unknown not logged in".
        try:
            if await target.evaluate(LOGIN_GATE_JS):
                return "logged_out_or_session_expired"
        except Exception:
            pass
        return "unknown_not_logged_in"

    # ── Element finding with fallbacks ────────────────────

    async def _find(self, css: list[str] | None = None,
                    text: str | None = None,
                    role: str | None = None,
                    label: str | None = None,
                    timeout: int = 8,
                    parent: Locator | Page | None = None,
                    use_last: bool = False,
                    visible_only: bool = False) -> Locator | None:
        ctx = parent or self.page

        async def _pick(loc):
            if not visible_only:
                return loc.last if use_last else loc.first
            cnt = await loc.count()
            if cnt == 0:
                return None
            rng = range(cnt - 1, -1, -1) if use_last else range(cnt)
            for i in rng:
                el = loc.nth(i)
                if await el.is_visible():
                    return el
            return None

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if role:
                try:
                    base = ctx.get_by_role(role, name=text, exact=False) if text else ctx.get_by_role(role)
                    loc = await _pick(base)
                    if loc is not None:
                        return loc
                except Exception:
                    pass

            if css:
                for sel in css:
                    try:
                        base = ctx.locator(sel)
                        loc = await _pick(base)
                        if loc is not None:
                            return loc
                    except Exception:
                        continue

            if text:
                try:
                    base = ctx.get_by_text(text, exact=False)
                    loc = await _pick(base)
                    if loc is not None:
                        return loc
                except Exception:
                    pass

            if label:
                try:
                    base = ctx.get_by_label(label, exact=False)
                    loc = await _pick(base)
                    if loc is not None:
                        return loc
                except Exception:
                    pass

            await asyncio.sleep(0.3)
        return None

    # ── Diagnostics: dump all interactive elements ────────

    async def _debug_dump(self, label: str):
        """Dump page buttons if debug mode is enabled."""
        if self.debug:
            await self._dump_page_buttons(label)

    async def _debug_screenshot(self, label: str, react_label: str | None = None):
        """Save a screenshot + DOM state dump for diagnosis. Always runs."""
        from datetime import datetime
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        folder = Path.home() / ".autoshare" / "debug"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{label}_{stamp}.png"
            await self.page.screenshot(path=str(path))
            self.log(f"📸 Screenshot saved → {path}")
        except Exception as e:
            self.log(f"  ⚠️  Could not save screenshot: {e}")
        await self._debug_dom_dump(label, react_label)

    async def _debug_dom_dump(self, label: str, react_label: str | None = None):
        """Save a JSON dump of the reaction-relevant DOM state. Always runs."""
        from datetime import datetime
        if react_label is None:
            return
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        folder = Path.home() / ".autoshare" / "debug"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            rl = react_label.lower()
            dom = await self.page.evaluate("""(rl) => {
                const info = (el) => {
                    const r = el.getBoundingClientRect();
                    const cs = getComputedStyle(el);
                    return {
                        tag: el.tagName,
                        role: el.getAttribute('role'),
                        aria: el.getAttribute('aria-label'),
                        alt: el.getAttribute('alt'),
                        title: el.getAttribute('title'),
                        text: (el.innerText || '').trim().slice(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        visible: el.offsetParent !== null && r.width > 0
                            && cs.display !== 'none' && cs.visibility !== 'hidden',
                    };
                };
                const all = [...document.querySelectorAll('div, span, img, a, button')];
                const matches = all.filter(e => {
                    const a = (e.getAttribute('aria-label') || '').toLowerCase();
                    const alt = (e.getAttribute('alt') || '').toLowerCase();
                    const t = (e.innerText || '').toLowerCase().trim();
                    const title = (e.getAttribute('title') || '').toLowerCase();
                    return (a === rl || alt === rl || t === rl || title === rl);
                }).slice(0, 25).map(info);
                const reactEl = matches.find(m => m.role === 'button' && m.aria && m.aria.toLowerCase() === rl) || matches[0];
                let at_press_point = null;
                if (reactEl && reactEl.w > 0) {
                    const cx = reactEl.x + reactEl.w / 2;
                    const cy = reactEl.y + reactEl.h / 2;
                    at_press_point = document.elementsFromPoint(cx, cy).slice(0, 8).map(info);
                }
                return {
                    url: location.href,
                    target: rl,
                    matches,
                    at_press_point,
                    like_btn: (() => {
                        const el = document.getElementById('_fb_like_btn');
                        return el ? info(el) : null;
                    })(),
                    reaction_btn: (() => {
                        const el = document.getElementById('_fb_reaction_btn');
                        return el ? info(el) : null;
                    })(),
                    overlays: [...document.querySelectorAll(
                        '[role="toolbar"], [role="menu"], [role="dialog"], [data-testid="react_buttons_root"]'
                    )].slice(0, 8).map(info),
                };
            }""", rl)
            dump_path = folder / f"{label}_{stamp}.json"
            dump_path.write_text(json.dumps(dom, indent=2, ensure_ascii=False), encoding="utf-8")
            self.log(f"📋 DOM dump saved → {dump_path}")
        except Exception as e:
            self.log(f"  ⚠️  Could not save DOM dump: {e}")

    # ── Resource-heavy content blocking ──────────────────────────────────────────

    async def _enable_resource_blocking(self, page):
        """Block images, media, and fonts to save ~40-50% RAM.

        Facebook loads hundreds of images and videos per page that aren't
        needed for automation (button clicks work fine without them).
        Blocking these resource types dramatically reduces:
        - Renderer memory (no decoded images)
        - Network bandwidth (fewer requests)
        - DOM tree size (no img/video elements with data)

        NOTE: We intentionally do NOT block stylesheets — Facebook's
        layout, visibility detection, and coordinate-based clicking
        all depend on CSS being loaded.

        Blocking is live-toggleable via ``self._block_resources``: the
        comment flow turns it OFF because Facebook does not render the
        comment composer when the post's resources are blocked.
        """
        if getattr(self, "_block_resources", None) is None:
            self._block_resources = True

        async def _route(route):
            try:
                if (self._block_resources and route.request.resource_type
                        in ("image", "media", "font")):
                    await route.abort()
                else:
                    await route.continue_()
            except Exception:
                try:
                    await route.continue_()
                except Exception:
                    pass

        try:
            await page.route("**/*", _route)
        except Exception:
            pass

    # ── Share flow: helpers ────────────────────────────────

    async def _verify_post_shared(self) -> bool:
        """Check for Facebook's toast/notification after a share action.
        Looks for specific visible [role="alert"] or [aria-live="polite"] elements
        that Facebook uses for success/error toasts, not the entire page body.
        Also checks if the URL actually changed from the original post URL
        (a real redirect means the share was accepted).

        Sets self._share_toast_confirmed when Facebook said so in its own
        words, which later steps trust over a dialog left on screen. Cleared
        first, so the Timeline share's verdict can never leak into the Story
        share that follows it.
        """
        self._share_toast_confirmed = False
        await asyncio.sleep(1)
        try:
            result = await self.page.evaluate('''() => {
                // Check visible alert elements (Facebook toasts)
                const alerts = [...document.querySelectorAll('[role="alert"]')]
                    .filter(el => el.offsetParent !== null && el.innerText.trim());
                for (const el of alerts) {
                    const t = el.innerText.toLowerCase().substring(0, 200);
                    const err = ["went wrong", "try again", "can't", "failed",
                                "blocked", "restricted", "not available", "error"];
                    const ok = ["shared to", "your post was", "posted to", "shared"];
                    if (err.some(kw => t.includes(kw))) return "error::" + el.innerText.trim().slice(0, 200);
                    if (ok.some(kw => t.includes(kw))) return "success";
                }
                // Check aria-live regions (another toast pattern)
                const live = [...document.querySelectorAll('[aria-live="polite"]')]
                    .filter(el => el.offsetParent !== null && el.innerText.trim());
                for (const el of live) {
                    const t = el.innerText.toLowerCase().substring(0, 200);
                    const err = ["went wrong", "can't", "failed", "error"];
                    const ok = ["shared to", "your post", "posted", "shared"];
                    if (err.some(kw => t.includes(kw))) return "error::" + el.innerText.trim().slice(0, 200);
                    if (ok.some(kw => t.includes(kw))) return "success";
                }
                return "unknown";
            }''')

            if isinstance(result, str) and result.startswith("error"):
                said = result.split("::", 1)[1].strip() if "::" in result else ""
                self.last_share_error = said
                self.log("Error toast detected — share was rejected by Facebook"
                         + (f': "{said}"' if said else " (no text captured)"))
                await self._debug_dump("share_error_toast")
                return False
            if result == "success":
                self._share_toast_confirmed = True
                self.log("Success toast detected — share went through!")
                return True

            # No toast visible — check if URL actually changed from the original post URL
            # (avoids false positive when current URL still contains /videos/ from navigation)
            try:
                current_url = self.page.url.lower()
                original_url = (self._post_url_before_share or "").lower()
                if original_url and current_url != original_url:
                    if any(p in current_url for p in ["/posts/", "/photos/", "story.php", "/videos/"]):
                        self.log("URL changed from original post — share went through")
                        return True
            except Exception:
                pass

            # Modal closed, no errors — assume success
            return True
        except Exception as e:
            self.log(f"Could not verify share status: {e}")
            return True

    async def _back_on_target_post(self, step: str) -> bool:
        """Make sure the page is still on the post being shared.

        Facebook navigates away by itself - a completed share lands on the new
        post or bounces to the feed (observed: facebook.com/?__tn__=F-R). Every
        share step then searched THAT page for a Share button, page-wide, and
        happily found one belonging to a stranger's feed post: a run shared a
        post with 102.7K likes, 1675px from the viewport centre, to an
        account's Story instead of the target video.

        Returns False only when the page is off-target and cannot be brought
        back, which must abort the step rather than share something else.
        """
        target = getattr(self, "_share_post_url", "") or ""
        if not target:
            return True                      # nothing to compare against
        try:
            current = await self.page.evaluate("window.location.href") or ""
        except Exception:
            return True                      # mid-navigation; let the step try
        post_id = getattr(self, "_target_post_id", None)
        on_post = bool(post_id) and post_id in current
        if on_post or (current and current.rstrip("/") == target.rstrip("/")):
            return True
        if not self._is_home_url(current) and post_id and post_id in current:
            return True
        self.log(f"  ↩️  Page drifted to {current[:70]} before {step} - "
                 f"returning to the post")
        try:
            await self.page.goto(target, timeout=30000,
                                 wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))
            return True
        except Exception as e:
            self.log(f"  ⚠️  Could not return to the post: {str(e)[:90]}")
            return False

    # Facebook's "Something went wrong. Please try again." is a transient
    # server-side refusal, not a verdict about the account or the post: in the
    # same batch, the same post, other profiles went through seconds later.
    # It is also safe to retry - the post's share counter never moved on a
    # rejected attempt, so nothing was posted to duplicate.
    SHARE_RETRY_ATTEMPTS = 3
    _SHARE_TRANSIENT = ("something went wrong", "please try again",
                        "try again later", "temporarily unavailable",
                        "couldn't load", "could not load")

    # What Facebook's API says when the account itself is the problem. The
    # toast never shows any of this - it reads "Something went wrong. Please
    # try again.", which is why a restricted account was retried three times.
    # Captured live from a refused share: {"message":"Your account is
    # restricted"} with {"code":1404078}.
    _SHARE_RESTRICTION_TEXT = ("account is restricted", "temporarily blocked",
                               "temporarily restricted", "you can't share",
                               "cannot share", "action blocked",
                               "we limit how often", "abusive", "spam")
    _SHARE_RESTRICTION_CODES = ("1404078", "1404102", "1404006", "368")

    async def _watch_share_api_errors(self):
        """Record what Facebook's GraphQL replies say while a share is tried.

        Returns the detach callable. The toast is deliberately vague, so the
        only way to tell "the server hiccuped" from "this account may not
        share" is to read the API's own words.
        """
        self._share_api_errors = []

        async def _on_response(resp):
            try:
                if "/api/graphql" not in resp.url:
                    return
                body = await resp.text()
            except Exception:
                return
            low = body.lower()
            if not any(t in low for t in self._SHARE_RESTRICTION_TEXT) \
                    and not any(f'"{c}"' in body or f":{c}" in body
                                for c in self._SHARE_RESTRICTION_CODES):
                return
            for m in re.finditer(r'"(?:message|error_user_msg|error_user_title|'
                                 r'summary)"\s*:\s*"([^"]{4,200})"', body):
                self._share_api_errors.append(m.group(1))
            for c in self._SHARE_RESTRICTION_CODES:
                if f":{c}" in body:
                    self._share_api_errors.append(f"code {c}")

        try:
            self.page.on("response", _on_response)
        except Exception:
            return lambda: None

        def _detach():
            try:
                self.page.remove_listener("response", _on_response)
            except Exception:
                pass
        return _detach

    def _share_restriction_seen(self) -> str:
        """Facebook's own reason, when it says the ACCOUNT cannot share."""
        for said in getattr(self, "_share_api_errors", []) or []:
            low = said.lower()
            if any(t in low for t in self._SHARE_RESTRICTION_TEXT) \
                    or said.startswith("code "):
                return said
        return ""

    def _share_error_is_transient(self) -> bool:
        # An account restriction outranks the toast. "Something went wrong.
        # Please try again." is what Facebook shows for BOTH a real hiccup and
        # a restricted account, and retrying the second only spends the
        # account's remaining goodwill.
        if self._share_restriction_seen():
            return False
        said = (getattr(self, "last_share_error", "") or "").lower()
        return any(kw in said for kw in self._SHARE_TRANSIENT)

    async def _clear_share_dialog(self):
        """Close whatever is on screen so a retry starts from the post."""
        for _ in range(2):
            try:
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(0.8)
            except Exception:
                break

    async def _share_once(self, options: tuple, what: str) -> bool:
        """One share attempt. options are the modal labels to try, in order."""
        # Cleared per attempt: a stale message from an earlier attempt would
        # make an unrelated failure look like a retryable one.
        self.last_share_error = ""
        await self._debug_dump(f"{what.lower()}_before_share_btn")
        # Capture URL right before sharing for reliable redirect detection
        try:
            self._post_url_before_share = await self.page.evaluate("window.location.href") or ""
        except Exception:
            self._post_url_before_share = ""
        self.log(f"Sharing to {what}...")

        share_result = await self._click_share_button()
        if share_result == "already_shared":
            self.log(f"⏭️  Skipping {what} share (already shared)")
            return True
        if not share_result:
            return False

        # Popup opened — wait for it to fully render before clicking options
        await asyncio.sleep(random.uniform(1, 2))

        # First label that works wins. Never evaluate the rest: clicking a
        # second option after one already took would act twice.
        picked = False
        for opt in options:
            if await self._pick_option_in_modal(opt):
                picked = True
                break
        if not picked:
            return False
        # Check for toast immediately after clicking (before it disappears)
        if not await self._verify_post_shared():
            return False
        delay = random.uniform(5, 10)
        self.log(f"Waiting {delay:.0f}s for {what} share...")
        await asyncio.sleep(delay)
        if await self._is_modal_still_open():
            if getattr(self, "_share_toast_confirmed", False):
                # Facebook confirmed the share in its own toast and the post's
                # share count went up; a dialog left on screen afterwards is
                # cosmetic. Dismiss it so the next step starts clean.
                self.log("Share confirmed by toast; dismissing the dialog "
                         "Facebook left open")
                await self._clear_share_dialog()
                return True
            self.log("Share modal still open after wait — share may have failed")
            return False
        return True

    # The share sheet offers two routes to a timeline post: "Share Now", which
    # posts in one click, and an option that opens the full composer, where a
    # Post button commits it. They are different server calls, so a refusal of
    # one is not a refusal of the other - which is the whole point of trying
    # the second when the first is turned down.
    COMPOSER_SHARE_OPTIONS = ("Share to Feed", "Share to News Feed",
                              "Write Post", "Share to feed")

    async def _composer_option_offered(self) -> str | None:
        """The composer option this share sheet offers, if it offers one.

        One DOM pass, no waiting. Asking _pick_option_in_modal for four labels
        in turn cost ~20s per retry on a post that has none of them, and a
        video's sheet has none: it is itself the composer, with "Share now" as
        its submit.
        """
        try:
            return await self.page.evaluate("""(labels) => {
                const vis = e => { const r = e.getBoundingClientRect();
                                   return r.width > 0 && r.height > 0; };
                for (const d of document.querySelectorAll('[role="dialog"]')) {
                    if (!vis(d)) continue;
                    for (const el of d.querySelectorAll(
                            '[role="menuitem"], [role="button"]')) {
                        if (!vis(el)) continue;
                        const t = (el.innerText || '').trim().toLowerCase();
                        const a = (el.getAttribute('aria-label') || '').toLowerCase();
                        for (const want of labels) {
                            const w = want.toLowerCase();
                            if (t === w || a === w) return want;
                        }
                    }
                }
                return null;
            }""", list(self.COMPOSER_SHARE_OPTIONS))
        except Exception:
            return None

    async def _share_via_composer(self, what: str):
        """Share through the full composer.

        True shared, False the composer was there and failed, None this post
        offers no composer route - the caller then uses the quick route rather
        than treating a missing option as a refusal.
        """
        if not await self._click_share_button():
            return False
        await asyncio.sleep(random.uniform(1, 2))

        option = await self._composer_option_offered()
        if option is None:
            self.log("  No composer route on this post - its share sheet is "
                     "the composer")
            await self._clear_share_dialog()
            return None

        self.last_share_error = ""
        self.log(f"Sharing to {what} through the composer ('{option}')...")
        if not await self._pick_option_in_modal(option):
            return False

        await asyncio.sleep(random.uniform(2, 3))
        post_btn = await self._find(css=self.COMPOSER_POST_SELECTORS,
                                    timeout=20, visible_only=True)
        if not post_btn:
            self.log("  Composer opened but its Post button never appeared")
            return False
        try:
            await post_btn.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.4, 0.9))
            await post_btn.click(timeout=8000)
        except Exception as e:
            self.log(f"  Could not click the composer's Post button: {str(e)[:90]}")
            return False
        if not await self._verify_post_shared():
            return False
        await asyncio.sleep(random.uniform(4, 8))
        if await self._is_modal_still_open() and not getattr(
                self, "_share_toast_confirmed", False):
            self.log("  Composer still open after posting — treating as failed")
            return False
        await self._clear_share_dialog()
        return True

    async def _share_with_retry(self, options: tuple, what: str) -> bool:
        """Share, retrying only Facebook's own "try again" style refusals.

        A retry does not repeat the same click. Facebook refused "Share Now"
        three times in a row on one post while accepting it from another
        profile seconds earlier, so repeating it is not a strategy - the
        second and third attempts go through the composer, which is a
        different call, and only fall back to the quick route if this post
        does not offer a composer at all.
        """
        detach = await self._watch_share_api_errors()
        try:
            return await self._share_attempts(options, what)
        finally:
            detach()

    async def _share_attempts(self, options: tuple, what: str) -> bool:
        for attempt in range(1, self.SHARE_RETRY_ATTEMPTS + 1):
            if not await self._back_on_target_post(f"the {what} share"):
                return False
            if attempt > 1 and what == "Timeline":
                # None means this post's share sheet has no composer route at
                # all, which is the normal case: the sheet IS the composer,
                # with "Share now" as its submit. Only an actual composer
                # failure is worth judging; otherwise fall straight through.
                composed = await self._share_via_composer(what)
                if composed:
                    return True
                if composed is False:
                    if not self._share_error_is_transient():
                        return False
                    if not await self._back_on_target_post(f"the {what} share"):
                        return False
            if await self._share_once(options, what):
                return True
            if not self._share_error_is_transient():
                blocked = self._share_restriction_seen()
                if blocked:
                    # Say what Facebook actually said. The toast claims a
                    # generic hiccup; the API named the account.
                    self.last_share_error = (
                        f"Facebook is restricting this account from sharing "
                        f"(API said: {blocked})")
                    self.log(f"  {what} share refused - {self.last_share_error}")
                return False            # a real refusal - retrying is pointless
            if attempt == self.SHARE_RETRY_ATTEMPTS:
                self.log(f"  {what} share still refused after "
                         f"{self.SHARE_RETRY_ATTEMPTS} attempts - giving up")
                return False
            wait = random.uniform(8, 20) * attempt
            self.log(f"  ↻ Facebook said \"{self.last_share_error}\" - "
                     f"retrying {what} share in {wait:.0f}s "
                     f"(attempt {attempt + 1}/{self.SHARE_RETRY_ATTEMPTS})")
            await self._clear_share_dialog()
            await asyncio.sleep(wait)
        return False

    async def _share_to_timeline(self) -> bool:
        """Click Share → 'Share Now' to post to timeline."""
        return await self._share_with_retry(("Share Now", "Share to feed"),
                                            "Timeline")

    async def _share_to_story(self) -> bool:
        """Click Share → 'Your Story' to post to story."""
        return await self._share_with_retry(("Your Story",), "Story")

    # ── Share flow ────────────────────────────────────────

    async def _is_already_shared(self) -> bool:
        """Check if this post is already shared by the current profile.
        Looks for 'Shared' text/aria-label on the Share button itself
        or 'Shared with' indicators on the post.
        NOTE: 'Shared with Public' on the privacy button is NOT an already-shared indicator."""
        try:
            result = await self.page.evaluate('''() => {
                // Check Share button text — if it says "Shared" instead of "Share"
                const buttons = [...document.querySelectorAll('[aria-label*="share" i], [aria-label*="shared" i], [role="button"]')];
                for (const btn of buttons) {
                    const a = (btn.getAttribute('aria-label') || '').toLowerCase();
                    const t = (btn.innerText || '').trim().toLowerCase();
                    if (btn.offsetParent !== null) {
                        // "Shared with Public" is a PRIVACY indicator, not an already-shared flag — skip it
                        if (a.includes('shared with')) continue;
                        // Check if button says "Shared" or "Already Shared"
                        if (a.includes('shared') && !a.includes('share to') && !a.includes('share this'))
                            return a;
                        if (t === 'shared' || t.includes('already shared'))
                            return t;
                    }
                }
                // Check for "Shared" indicator near the post (but NOT "Shared with Public" privacy text)
                const shared = document.evaluate(
                    '//span[contains(translate(text(),\"ABCDEFGHIJKLMNOPQRSTUVWXYZ\",\"abcdefghijklmnopqrstuvwxyz\"),\"shared\")]',
                    document, null, XPathResult.ANY_TYPE, null
                );
                let el = shared.iterateNext();
                while (el) {
                    const text = (el.textContent || '').toLowerCase().trim();
                    // Skip "Shared with Public/Only Me/Friends" — these are privacy indicators
                    if (text.startsWith('shared with')) {
                        el = shared.iterateNext();
                        continue;
                    }
                    if (el.offsetParent !== null) return text;
                    el = shared.iterateNext();
                }
                return null;
            }''')
            if result:
                self.log(f"Post appears already shared: '{result}'")
                return True
        except Exception:
            pass
        return False

    async def _delete_old_share_from_timeline(self, original_post_url: str) -> bool:
        """Navigate to profile timeline and delete the old share of this post.
        Uses multiple strategies to find and delete shared posts."""
        try:
            self.log("📍 Navigating to profile timeline...")
            await self.page.goto("https://www.facebook.com/me", timeout=30000, wait_until="load")
            await asyncio.sleep(5)  # Extra time for timeline to render
            
            # Scroll down to load recent posts
            self.log("📜 Scrolling timeline to load posts...")
            for i in range(15):
                await self.page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(1)
            
            self.log(f"🔍 Searching for shared posts to delete...")
            
            # Strategy: Find ANY post with a visible menu button and delete it
            # This is more aggressive but effective for clearing recent shares
            result = await self.page.evaluate('''() => {
                const articles = [...document.querySelectorAll('[role="article"]')];
                
                // Debug: Count articles
                if (articles.length === 0) return {error: 'no_articles'};
                
                // Try to find the first article with an action menu
                for (let i = 0; i < Math.min(articles.length, 10); i++) {
                    const article = articles[i];
                    
                    // Get article text for debugging
                    const articleText = (article.innerText || '').substring(0, 200);
                    
                    // Look for menu button (various patterns)
                    const buttons = [...article.querySelectorAll('[role="button"]')];
                    let menuBtn = null;
                    
                    for (const btn of buttons) {
                        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const text = (btn.innerText || '').trim().toLowerCase();
                        
                        // Match menu patterns — broad matching for Facebook's "..." button
                        if (aria.includes('action') || aria.includes('more') || 
                            aria.includes('option') || aria.includes('menu') ||
                            text === '...' || text === '⋯' || text === '•••' ||
                            text === '…' || aria.includes('expand') ||
                            aria.includes('hide') || aria.includes('remove')) {
                            
                            // Make sure button is visible
                            if (btn.offsetParent !== null) {
                                menuBtn = btn;
                                break;
                            }
                        }
                    }
                    
                    // Fallback: look for SVG-only buttons (Facebook's "..." uses SVG icon)
                    if (!menuBtn) {
                        // Find small buttons with no visible text (likely icon-only menu triggers)
                        for (const btn of buttons) {
                            if (btn.offsetParent === null) continue;
                            const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                            const text = (btn.innerText || '').trim();
                            // Skip well-known non-menu buttons
                            if (aria.includes('like') || aria.includes('comment') || 
                                aria.includes('share') || aria.includes('send') ||
                                aria.includes('reaction') || aria.includes('follow') ||
                                aria.includes('save') || text.length > 15) continue;
                            // Check if it's a small icon-only button (likely "...")
                            const rect = btn.getBoundingClientRect();
                            if (rect.width < 50 && rect.height < 50 && (text.length <= 1 || btn.querySelector('svg'))) {
                                menuBtn = btn;
                                break;
                            }
                        }
                    }
                    
                    if (menuBtn) {
                        menuBtn.click();
                        return {
                            success: true, 
                            action: 'menu_opened',
                            articlePreview: articleText
                        };
                    }
                }
                
                return {
                    error: 'no_menu_found',
                    articleCount: articles.length,
                    firstArticleText: articles[0] ? (articles[0].innerText || '').substring(0, 200) : 'none'
                };
            }''')
            
            # Debug logging
            if isinstance(result, dict):
                if result.get('error'):
                    self.log(f"⚠️  Timeline search issue: {result.get('error')}")
                    if result.get('articleCount'):
                        self.log(f"   Found {result['articleCount']} articles")
                        self.log(f"   First article preview: {result.get('firstArticleText', 'N/A')[:100]}")
                    return False
                    
                if result.get('action') == 'menu_opened':
                    self.log(f"✓ Opened menu on post")
                    await asyncio.sleep(2)
                    
                    # Look for Delete option
                    self.log("📋 Looking for Delete option...")
                    delete_clicked = await self.page.evaluate('''() => {
                        // First try menuitem role
                        const menuItems = [...document.querySelectorAll('[role="menuitem"]')];
                        for (const item of menuItems) {
                            const text = (item.innerText || item.textContent || '').trim().toLowerCase();
                            if (text.includes('delete') || text.includes('remove') || 
                                text.includes('move to trash')) {
                                if (item.offsetParent !== null) {
                                    item.click();
                                    return 'clicked';
                                }
                            }
                        }
                        
                        // Fallback: any visible element with delete text
                        const allElements = [...document.querySelectorAll('div, span, button')];
                        for (const el of allElements) {
                            const text = (el.innerText || '').trim().toLowerCase();
                            if (text === 'delete' || text === 'delete post') {
                                if (el.offsetParent !== null) {
                                    el.click();
                                    return 'clicked_fallback';
                                }
                            }
                        }
                        
                        return null;
                    }''')
                    
                    if delete_clicked:
                        self.log(f"✓ Delete option clicked ({delete_clicked})")
                        await asyncio.sleep(2)
                        
                        # Confirm deletion
                        confirmed = await self.page.evaluate('''() => {
                            const buttons = [...document.querySelectorAll('[role="button"]')];
                            for (const btn of buttons) {
                                const text = (btn.innerText || '').trim().toLowerCase();
                                if (text === 'delete' || text === 'confirm' || text === 'move to trash') {
                                    btn.click();
                                    return true;
                                }
                            }
                            return false;
                        }''')
                        
                        if confirmed:
                            self.log("✅ Successfully deleted a post from timeline")
                            await asyncio.sleep(2)
                            return True
                        else:
                            self.log("⚠️  Could not confirm deletion")
                    else:
                        self.log("⚠️  Could not find Delete option in menu")
            
            return False
            
        except Exception as e:
            self.log(f"❌ Error deleting old share: {e}")
            self.log(f"   Traceback: {traceback.format_exc()}")
            return False

    async def _click_share_button(self) -> bool:
        """Find and click the Share button on a post, wait for modal.
        If the popup doesn't appear, retries with alternative Share button
        (first match instead of last, different selectors)."""
        self.log("Looking for Share button...")

        async def _share_popup_visible() -> bool:
            """Check if the share menu/popup is visible via fast JS evaluation.
            Facebook can render the share menu as:
            - [role="dialog"] / [role="menu"] (standard modal)
            - Direct role="button" options without a container (video/reel posts)
            - Bottom sheet or overlay popover
            This checks all patterns in a single evaluate() call (<10ms)."""
            try:
                return bool(await self.page.evaluate('''() => {
                    // Pattern 1: standard dialog or menu
                    const dialog = document.querySelector('[role="dialog"]');
                    if (dialog && dialog.offsetParent != null) return true;
                    const menu = document.querySelector('[role="menu"]');
                    if (menu && menu.offsetParent != null) return true;
                    // Pattern 2: share options as direct role="button" on page (video/reel posts)
                    const opts = [...document.querySelectorAll('[role="button"]')]
                        .filter(el => el.offsetParent != null)
                        .map(el => (el.innerText || "").trim().toLowerCase());
                    if (["share now", "your story", "copy link", "friend's profile",
                         "share to a group", "send in messenger", "embed",
                         "copy link to post", "send link"]
                        .some(t => opts.includes(t))) return true;
                    // Pattern 3: check for any new overlay/popover (bottom sheet on mobile/reels)
                    const overlays = document.querySelectorAll(
                        '[data-testid="reshare-tooltip"], [class*="tooltip"], [class*="popover"], [class*="bottom-sheet"]'
                    );
                    for (const o of overlays) {
                        if (o.offsetParent != null) return true;
                    }
                    // Pattern 4: check for a visible listbox or list with share options
                    const lists = document.querySelectorAll('[role="listbox"], [role="list"]');
                    for (const l of lists) {
                        if (l.offsetParent != null) {
                            const txt = (l.innerText || "").toLowerCase();
                            if (txt.includes("share") || txt.includes("story") || txt.includes("copy link"))
                                return true;
                        }
                    }
                    return false;
                }'''))
            except Exception:
                return False

        async def _try_click(use_last: bool):
            """Try clicking a Share button and wait for popup.
            Returns True if popup appeared, False if button found but no popup,
            None if no Share button found at all."""
            
            # Enhanced Share button detection with multiple strategies
            share_el = None
            target_id = getattr(self, '_target_post_id', None)
            
            # Strategy 0: Find Share button within the specific article containing the target post
            if target_id:
                found = await self.page.evaluate('''(targetId) => {
                    // Find the article that contains the target post ID
                    const articles = [...document.querySelectorAll('[role="article"]')];
                    let targetArticle = null;
                    for (const art of articles) {
                        const html = art.innerHTML || '';
                        if (html.includes(targetId)) {
                            targetArticle = art;
                            break;
                        }
                    }
                    if (!targetArticle) return false;
                    
                    // Look for Share button ONLY within this article
                    const buttons = [...targetArticle.querySelectorAll('[role="button"]')];
                    for (const btn of buttons) {
                        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const text = (btn.innerText || '').trim().toLowerCase();
                        if ((aria === 'share' || text === 'share') && btn.offsetParent !== null) {
                            btn.setAttribute('data-share-btn-target', 'true');
                            return true;
                        }
                    }
                    return false;
                }''', target_id)
                
                if found:
                    share_el = await self.page.query_selector('[data-share-btn-target="true"]')
                    if share_el:
                        self.log(f"  ✅ Found Share button in article for post {target_id}")
            
            # Strategy 1b: Reels/video page — pick the Share button closest to viewport center
            # On Reels pages there are no articles, but multiple Share buttons visible.
            # The active/target video is always the one centered in the viewport.
            if not share_el:
                found_center = await self.page.evaluate('''() => {
                    const centerX = window.innerWidth / 2;
                    const centerY = window.innerHeight / 2;
                    
                    const allShareBtns = [...document.querySelectorAll('[role="button"]')]
                        .filter(el => {
                            if (el.offsetParent === null) return false;
                            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                            const text = (el.innerText || '').trim().toLowerCase();
                            return aria === 'share' || text === 'share';
                        });
                    
                    if (allShareBtns.length <= 1) return false;  // No ambiguity, regular search is fine
                    
                    // Find the one closest to viewport center (the active Reel)
                    let best = null;
                    let bestDist = Infinity;
                    for (const btn of allShareBtns) {
                        const rect = btn.getBoundingClientRect();
                        const btnX = rect.left + rect.width / 2;
                        const btnY = rect.top + rect.height / 2;
                        const dist = Math.sqrt((btnX - centerX) ** 2 + (btnY - centerY) ** 2);
                        if (dist < bestDist) {
                            bestDist = dist;
                            best = btn;
                        }
                    }
                    
                    if (best) {
                        best.setAttribute('data-share-btn-target', 'true');
                        return true;
                    }
                    return false;
                }''')
                
                if found_center:
                    share_el = await self.page.query_selector('[data-share-btn-target="true"]')
                    if share_el:
                        self.log("  ✅ Found Share button closest to viewport center (active Reel)")
            
            # Strategy 1: Standard aria-label search (page-wide fallback)
            # NOTE: Excluding [aria-label*="Shared with" i] — that's the privacy indicator, not the share button
            if not share_el:
                share_el = await self._find(
                    css=[
                        '[aria-label="Share"]',
                        '[aria-label*="Send this to friends" i]',
                        '[data-testid*="share"]',
                        '[role="button"]:has-text-is("Share")',
                    ],
                    timeout=8,
                    use_last=use_last,
                    visible_only=True,
                )
            
            # Strategy 2: If not found, search by JavaScript (more flexible, page-wide)
            if not share_el:
                self.log("  Standard search failed, trying JavaScript search...")
                found = await self.page.evaluate('''({useLast, targetId}) => {
                    const centerX = window.innerWidth / 2;
                    const centerY = window.innerHeight / 2;
                    
                    const buttons = [...document.querySelectorAll('[role="button"]')]
                        .filter(el => el.offsetParent !== null);
                    
                    // Score candidates: prefer buttons inside the correct article
                    // On Reels pages, prefer the one closest to viewport center
                    const candidates = [];
                    for (const btn of buttons) {
                        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                        const text = (btn.innerText || '').trim().toLowerCase();
                        
                        // Match exact "share" or aria-label "share" (NOT "shared with..." privacy button)
                        const isShareBtn = (
                            aria === 'share' ||
                            aria.startsWith('send this to friends') ||
                            text === 'share'
                        );
                        if (isShareBtn) {
                            let score = 0;
                            // +10: inside the target article
                            if (targetId) {
                                let parent = btn.parentElement;
                                for (let i = 0; i < 15 && parent; i++) {
                                    if (parent.innerHTML && parent.innerHTML.includes(targetId)) {
                                        score = 10;
                                        break;
                                    }
                                    parent = parent.parentElement;
                                }
                            }
                            // +8: closest to viewport center (active Reel on video pages)
                            if (score < 8) {
                                const rect = btn.getBoundingClientRect();
                                const btnX = rect.left + rect.width / 2;
                                const btnY = rect.top + rect.height / 2;
                                const dist = Math.sqrt((btnX - centerX) ** 2 + (btnY - centerY) ** 2);
                                const maxDist = Math.sqrt(centerX ** 2 + centerY ** 2);
                                const proximity = Math.max(0, 8 - Math.floor((dist / maxDist) * 8));
                                score = Math.max(score, proximity);
                            }
                            // +5: has Like/Comment siblings (action bar pattern)
                            if (score < 5) {
                                const siblings = [...(btn.parentElement?.children || [])];
                                const hasLike = siblings.some(s => 
                                    (s.getAttribute('aria-label') || '').toLowerCase().includes('like'));
                                if (hasLike) score = 5;
                            }
                            candidates.push({el: btn, score: score});
                            btn.setAttribute('data-share-btn-found', 'true');
                        }
                    }
                    
                    if (candidates.length === 0) return false;
                    
                    // Sort by score descending, then take first/last
                    candidates.sort((a, b) => b.score - a.score);
                    const target = useLast ? candidates[candidates.length - 1].el : candidates[0].el;
                    target.setAttribute('data-share-btn-target', 'true');
                    return true;
                }''', {"useLast": use_last, "targetId": target_id})
                
                if found:
                    share_el = await self.page.query_selector('[data-share-btn-target="true"]')
                    if share_el:
                        self.log("  ✅ Found Share button via JavaScript")
            
            if not share_el:
                # Log what buttons ARE available for debugging
                available_buttons = await self.page.evaluate('''() => {
                    const buttons = [...document.querySelectorAll('[role="button"]')]
                        .filter(el => el.offsetParent !== null)
                        .map(el => ({
                            text: (el.innerText || '').trim().substring(0, 30),
                            aria: (el.getAttribute('aria-label') || '').substring(0, 50)
                        }))
                        .filter(b => b.text || b.aria)
                        .slice(0, 10);  // First 10 buttons only
                    return buttons;
                }''')
                self.log(f"  ⚠️  Available buttons on page: {available_buttons}")
                return None  # No button found
            
            # Log which button we found for debugging
            btn_info = await share_el.evaluate('''(el) => {
                const rect = el.getBoundingClientRect();
                const cx = window.innerWidth / 2;
                const cy = window.innerHeight / 2;
                const bx = rect.left + rect.width / 2;
                const by = rect.top + rect.height / 2;
                const dist = Math.sqrt((bx - cx) ** 2 + (by - cy) ** 2);
                
                // Find nearby action buttons to identify which post this belongs to
                let context = '';
                let parent = el.parentElement;
                for (let i = 0; i < 10 && parent; i++) {
                    const likes = parent.querySelectorAll('[aria-label*="Like" i]');
                    const comments = parent.querySelectorAll('[aria-label*="Comment" i]');
                    if (likes.length > 0 || comments.length > 0) {
                        const likeText = likes.length > 0 ? likes[0].innerText || likes[0].getAttribute('aria-label') : '';
                        const commentText = comments.length > 0 ? comments[0].innerText || comments[0].getAttribute('aria-label') : '';
                        context = `Nearby: Like=${likeText}, Comment=${commentText}`;
                        break;
                    }
                    parent = parent.parentElement;
                }
                
                return {
                    text: (el.innerText || '').trim(),
                    ariaLabel: el.getAttribute('aria-label'),
                    visible: el.offsetParent !== null,
                    position: `(${bx.toFixed(0)}, ${by.toFixed(0)})`,
                    distFromCenter: dist.toFixed(0),
                    context: context
                };
            }''')
            self.log(f"  📍 Share button: text='{btn_info.get('text')}', aria='{btn_info.get('ariaLabel')}', pos={btn_info.get('position')}, dist_center={btn_info.get('distFromCenter')}px")
            if btn_info.get('context'):
                self.log(f"  📍 {btn_info.get('context')}")

            try:
                await share_el.wait_for_element_state("visible", timeout=5000)
            except Exception:
                pass
            await share_el.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            # Try multiple click methods for headless mode compatibility
            # Method 1: Force click
            await share_el.click(force=True)
            await asyncio.sleep(random.uniform(1.5, 2.5))

            for _ in range(8):
                if await _share_popup_visible():
                    return True
                await asyncio.sleep(0.3)

            # Method 2: JS click (re-find element to avoid stale reference)
            self.log("Popup didn't appear after force click, trying JS click...")
            try:
                # Re-find the button to avoid stale element
                share_el_fresh = await self.page.query_selector('[data-share-btn-target="true"]')
                if not share_el_fresh:
                    share_el_fresh = await self.page.query_selector('[aria-label*="Send this to friends" i], [aria-label="Share"]')
                
                if share_el_fresh:
                    await share_el_fresh.evaluate("el => el.click()")
                    await asyncio.sleep(2)
                    
                    for _ in range(5):
                        if await _share_popup_visible():
                            return True
                        await asyncio.sleep(0.3)
                else:
                    self.log("Could not re-find Share button for JS click")
            except Exception as e:
                self.log(f"JS click failed: {e}")
            
            # Method 3: Focus + Enter key (most reliable for headless)
            self.log("JS click failed, trying keyboard Enter...")
            try:
                # Re-find the button as element may be stale
                share_el_fresh = await self.page.query_selector('[data-share-btn-target="true"]')
                if not share_el_fresh:
                    # Fallback: search by aria-label again
                    share_el_fresh = await self.page.query_selector('[aria-label*="Send this to friends" i], [aria-label="Share"]')
                
                if share_el_fresh:
                    await share_el_fresh.focus()
                    await asyncio.sleep(0.5)
                    await self.page.keyboard.press("Enter")
                    await asyncio.sleep(2)
                    
                    for _ in range(5):
                        if await _share_popup_visible():
                            self.log("✅ Share popup opened via keyboard Enter!")
                            return True
                        await asyncio.sleep(0.3)
                else:
                    self.log("Could not re-find Share button for keyboard")
            except Exception as e:
                self.log(f"Keyboard Enter method failed: {e}")
            
            # Method 4: Try Space key
            self.log("Enter failed, trying Space key...")
            try:
                # Re-find the button again
                share_el_fresh = await self.page.query_selector('[data-share-btn-target="true"]')
                if not share_el_fresh:
                    share_el_fresh = await self.page.query_selector('[aria-label*="Send this to friends" i], [aria-label="Share"]')
                
                if share_el_fresh:
                    await share_el_fresh.focus()
                    await asyncio.sleep(0.5)
                    await self.page.keyboard.press("Space")
                    await asyncio.sleep(2)
                    
                    for _ in range(5):
                        if await _share_popup_visible():
                            self.log("✅ Share popup opened via Space key!")
                            return True
                        await asyncio.sleep(0.3)
                else:
                    self.log("Could not re-find Share button for Space key")
            except Exception as e:
                self.log(f"Space key method failed: {e}")
            
            # Method 5: Try direct mouse click with coordinates
            self.log("Space key failed, trying mouse click with coordinates...")
            try:
                share_el_fresh = await self.page.query_selector('[data-share-btn-target="true"]')
                if not share_el_fresh:
                    share_el_fresh = await self.page.query_selector('[aria-label*="Send this to friends" i], [aria-label="Share"]')
                
                if share_el_fresh:
                    # Get element position
                    box = await share_el_fresh.bounding_box()
                    if box:
                        # Click at center of element
                        x = box['x'] + box['width'] / 2
                        y = box['y'] + box['height'] / 2
                        self.log(f"  Clicking at coordinates ({x:.0f}, {y:.0f})")
                        await self.page.mouse.click(x, y)
                        await asyncio.sleep(2)
                        
                        for _ in range(5):
                            if await _share_popup_visible():
                                self.log("✅ Share popup opened via mouse click!")
                                return True
                            await asyncio.sleep(0.3)
                else:
                    self.log("Could not find Share button for mouse click")
            except Exception as e:
                self.log(f"Mouse click method failed: {e}")
            
            # Method 6: Advanced - Trigger React event handlers directly
            self.log("Mouse click failed, trying React event dispatch...")
            try:
                share_el_fresh = await self.page.query_selector('[data-share-btn-target="true"]')
                if not share_el_fresh:
                    share_el_fresh = await self.page.query_selector('[aria-label*="Send this to friends" i], [aria-label="Share"]')
                
                if share_el_fresh:
                    # Dispatch all possible events
                    await share_el_fresh.evaluate('''(element) => {
                        // Dispatch mousedown
                        element.dispatchEvent(new MouseEvent('mousedown', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            button: 0
                        }));
                        
                        // Dispatch mouseup
                        element.dispatchEvent(new MouseEvent('mouseup', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            button: 0
                        }));
                        
                        // Dispatch click
                        element.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            button: 0
                        }));
                        
                        // Dispatch pointerdown/up for React 17+
                        element.dispatchEvent(new PointerEvent('pointerdown', {
                            bubbles: true,
                            cancelable: true,
                            pointerId: 1,
                            pointerType: 'mouse'
                        }));
                        
                        element.dispatchEvent(new PointerEvent('pointerup', {
                            bubbles: true,
                            cancelable: true,
                            pointerId: 1,
                            pointerType: 'mouse'
                        }));
                    }''')
                    
                    await asyncio.sleep(2)
                    
                    for _ in range(5):
                        if await _share_popup_visible():
                            self.log("✅ Share popup opened via React events!")
                            return True
                        await asyncio.sleep(0.3)
                    
                    self.log("React event dispatch did not open popup")
                else:
                    self.log("Could not find Share button for React events")
            except Exception as e:
                self.log(f"React event dispatch failed: {e}")
            
            if await _share_popup_visible():
                return True

            return False  # Popup still didn't appear

        try:
            # Attempt 1: use_last=True (last Share button on page)
            ok = await _try_click(use_last=True)
            if ok is True:
                return True
            if ok is None:
                # No Share button found at all
                await self._dump_page_buttons("share")
                # Check if already shared (informational only)
                if await self._is_already_shared():
                    self.log("⚠️  WARNING: Facebook shows this post was already shared")
                self.log("Share button not found")
                return False

            # Attempt 2: use_last=False (first Share button)
            self.log("Popup didn't appear from last Share button — trying the first one...")
            await self._dump_page_buttons("share_popup_failed")
            ok = await _try_click(use_last=False)
            if ok is True:
                self.log("Share popup appeared from first Share button!")
                return True
            if ok is None:
                self.log("No alternative Share button found")
                if await self._is_already_shared():
                    self.log("⚠️  WARNING: Facebook shows this post was already shared")
                return False

            # Both failed — check if already shared and auto-retry with deletion
            self.log("Popup didn't appear from either Share button — checking if already shared...")
            await self._dump_page_buttons("share_final_failed")
            
            # Check if already shared
            if await self._is_already_shared():
                self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self.log("⚠️  POST ALREADY SHARED - ATTEMPTING AUTO-DELETE")
                self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                
                # Store the current URL to return to
                current_url = self.page.url
                
                # Try to delete the old share
                deleted = await self._delete_old_share_from_timeline(current_url)
                
                if deleted:
                    self.log("✅ Old share deleted successfully - retrying share...")
                    self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    
                    # Navigate back to the post
                    await self.page.goto(current_url, timeout=30000, wait_until="load")
                    await asyncio.sleep(3)
                    
                    # Retry clicking Share button (one attempt with first button)
                    self.log("🔄 RETRY: Looking for Share button after deletion...")
                    ok_retry = await _try_click(use_last=False)
                    if ok_retry is True:
                        self.log("✅ Share popup opened after deletion!")
                        return True
                    else:
                        self.log("❌ Share popup still didn't open after deletion")
                        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                        self.log("⚠️  TREATING AS SUCCESS (post already on timeline)")
                        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                        self.log("The post is already shared on this profile's Timeline.")
                        self.log("Facebook blocks re-sharing in headless mode even after deletion.")
                        self.log("Continuing with Story share (if enabled)...")
                        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                        return "already_shared"  # Signal caller to skip Share Now step
                else:
                    self.log("⚠️  Could not delete old share automatically")
                    self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    self.log("⚠️  TREATING AS SUCCESS (post already on timeline)")
                    self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    self.log("The post is already shared on this profile's Timeline.")
                    self.log("Auto-delete failed, but the share goal is already achieved.")
                    self.log("Continuing with Story share (if enabled)...")
                    self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                    return "already_shared"  # Signal caller to skip Share Now step
            
            # Return FALSE to indicate share failed
            return False
        except Exception as e:
            self.log(f"Could not click Share button: {e}")
            return False

    async def _is_modal_still_open(self) -> bool:
        """Check if the share dialog/modal is still visible after sharing.
        Looks for a dialog that contains share-related text to avoid
        false-matching unrelated dialogs (chat, notifications, etc.).
        """
        try:
            modal = self.page.locator('[role="dialog"]:visible').first
            if await modal.count() > 0 and await modal.is_visible():
                text = (await modal.inner_text() or "").lower()
                # Must look like the SHARE SHEET itself. The old list
                # included bare "share" and "post", which match nearly every
                # Facebook dialog - including the ones that only appear once a
                # share has succeeded, so a completed share read as a failure.
                if any(kw in text for kw in ("share now", "your story",
                                             "share to feed", "send this to",
                                             "write something about this")):
                    return True
        except Exception:
            pass
        return False

    async def _pick_option_in_modal(self, option_text: str) -> bool:
        """Click an option inside the share modal by its visible text."""
        self.log(f"Looking for '{option_text}' option...")
        try:
            opt = None
            for sel in (
                '[role="dialog"] [role="menuitem"]',
                '[role="menu"] [role="menuitem"]',
                '[role="dialog"] [role="button"]',
                '[role="menu"] [role="button"]',
            ):
                loc = self.page.locator(sel).filter(has_text=option_text).first
                if await loc.count() > 0 and await loc.is_visible():
                    opt = loc
                    break

            if not opt:
                opt = await self._find(text=option_text, timeout=4, visible_only=True)

            if not opt:
                await self._dump_page_buttons(option_text.replace(" ", "_").lower())
                self.log(f"'{option_text}' option not found")
                return False

            await opt.wait_for(state="visible", timeout=3000)
            await opt.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.3, 0.7))
            await opt.click(force=True)
            await asyncio.sleep(random.uniform(2, 3))
            return True
        except Exception as e:
            self.log(f"Could not click '{option_text}': {e}")
            return False

    async def _prepare_post_share(self, post_url: str) -> tuple[bool, str]:
        """Normalize the URL, navigate to the post, verify it's not the user's
        own post, and scroll the action buttons into view.

        Sets self._target_post_id for precise targeting.
        Returns (ok, message).
        """
        # Normalize Facebook URL to full format
        if post_url and not post_url.startswith("http"):
            post_url = f"https://www.facebook.com/{post_url}"
        
        # Convert mobile URLs to desktop URLs
        if post_url:
            post_url = post_url.replace("m.facebook.com", "www.facebook.com")
            post_url = post_url.replace("mobile.facebook.com", "www.facebook.com")
        
        # Extract the post/video ID from the URL for precise targeting
        self._target_post_id = None
        if post_url:
            # Match patterns like /videos/123, /posts/123, /photos/123, /reel/123, story.php?...id=123
            m = re.search(r'/(?:videos?|posts?|photos?|reels?)/(\d+)', post_url)
            if m:
                self._target_post_id = m.group(1)
            else:
                m = re.search(r'[?&](?:id|story_fbid)=(\d+)', post_url)
                if m:
                    self._target_post_id = m.group(1)
        if self._target_post_id:
            self.log(f"   Target post/video ID: {self._target_post_id}")
        
        # Remembered so every later step can put the page back on THIS post.
        # Facebook navigates away on its own after a share, and each step used
        # to just search whatever page it landed on.
        self._share_post_url = post_url

        self.log("Navigating to post URL...")
        self.log(f"   URL: {post_url}")

        for attempt in range(3):
            try:
                # "load" waits for every subresource, which on a live video
                # page means the stream itself - it timed out at 30s whenever
                # the machine was also running a watch. The DOM is all this
                # flow needs, and the settle sleep below covers the rest.
                await self.page.goto(post_url, timeout=30000,
                                     wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(2, 4))
                break
            except Exception as e:
                err = str(e)
                if "interrupted by another navigation" in err and attempt < 2:
                    self.log(f"Navigation interrupted (attempt {attempt+1}), retrying in 3s...")
                    await asyncio.sleep(3)
                    continue
                return False, f"Failed to load post URL: {err}"

        # A /share/v/<code>/ link is an interstitial: it resolves to the real
        # permalink a moment after domcontentloaded, and can read as
        # facebook.com/ while that is in flight. The share code carries no
        # numeric id, so until the resolved URL is known _target_post_id is
        # None and every later "am I still on the post?" check compares against
        # a URL the page will never have again. Settle it here, once.
        for _ in range(15):
            try:
                settled = await self.page.evaluate("window.location.href") or ""
            except Exception:
                break
            m = re.search(r'/(?:videos?|posts?|photos?|reels?)/(\d+)', settled)
            if m:
                if settled != post_url:
                    self.log(f"   Resolved to: {settled[:90]}")
                self._share_post_url = settled
                self._target_post_id = m.group(1)
                break
            await asyncio.sleep(1)

        self.log("Scrolling to reveal action buttons...")
        await self._debug_dump("share_before_share")
        
        # Check if this is the user's own post (can't share your own posts)
        is_own_post = await self.page.evaluate("""() => {
            // Look for "Edit post" or "Edit" button which only appears on own posts
            const buttons = [...document.querySelectorAll('[role="button"]')];
            for (const btn of buttons) {
                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                const text = (btn.innerText || '').toLowerCase();
                if (aria.includes('edit post') || text.includes('edit post') ||
                    (aria === 'edit' && btn.offsetParent !== null)) {
                    return true;
                }
            }
            
            // Also check for "Save post" or "Turn on notifications" which appear on own posts
            const menuItems = [...document.querySelectorAll('*')];
            for (const item of menuItems) {
                const text = (item.innerText || item.textContent || '').toLowerCase();
                if (text.includes('turn on notifications for this post') ||
                    text.includes('save post')) {
                    return true;
                }
            }
            
            return false;
        }""")
        
        if is_own_post:
            self.log("⚠️  This appears to be your own post - cannot share your own posts")
            return False, "Cannot share your own post"
        
        # Enhanced scrolling to ensure Share button is visible
        await self.page.evaluate("""(targetId) => {
            // First, close any open dialogs
            const closeButtons = [...document.querySelectorAll('[aria-label*="Close" i]')];
            closeButtons.forEach(btn => {
                if (btn.offsetParent !== null) {
                    try { btn.click(); } catch(e) {}
                }
            });
            
            // Find the correct article — try to match the target post/video ID
            const articles = [...document.querySelectorAll('[role="article"]')];
            let targetArticle = null;
            
            if (targetId && articles.length > 0) {
                // Search for an article that contains a link to the target post
                for (const art of articles) {
                    const html = art.innerHTML || '';
                    if (html.includes(targetId)) {
                        targetArticle = art;
                        break;
                    }
                }
            }
            
            // Fallback: first article if no match by ID
            if (!targetArticle && articles.length > 0) {
                targetArticle = articles[0];
            }
            
            if (targetArticle) {
                targetArticle.scrollIntoView({behavior: 'smooth', block: 'center'});
                window.scrollBy(0, 200);
            } else {
                // Reels/video page: no articles — scroll to keep the centered video's
                // action buttons in view. On Reels, the action buttons are typically
                // on the right side of the screen. Ensure they're visible.
                window.scrollBy(0, 100);
            }
        }""", self._target_post_id)
        await asyncio.sleep(2)
        return True, "ok"

    async def share_post_to_feed(self, post_url: str) -> tuple[bool, str]:
        """Share a post to the user's Timeline feed only."""
        ok, msg = await self._prepare_post_share(post_url)
        if not ok:
            return False, msg
        if not await self._share_to_timeline():
            return False, (getattr(self, "last_share_error", "")
                           or "Timeline share failed")
        return True, "Shared to Timeline"

    async def share_post_to_story(self, post_url: str) -> tuple[bool, str]:
        """Share a post to the user's Story only."""
        ok, msg = await self._prepare_post_share(post_url)
        if not ok:
            return False, msg
        if not await self._share_to_story():
            return False, (getattr(self, "last_share_error", "")
                           or "Story share failed")
        return True, "Shared to Story"

    async def share_post_to_timeline(self, post_url: str,
                                      comment_text: str | None = None,
                                      reaction: str | None = None) -> tuple[bool, str]:
        """Share a post to the user's Facebook Timeline (and optionally Story)."""
        step = 1

        ok, msg = await self._prepare_post_share(post_url)
        if not ok:
            return False, msg
        step += 1

        timeline_result = await self._share_to_timeline()
        if not timeline_result:
            # Carry the real reason out. "Timeline share failed" told the
            # caller nothing, so a refusal naming the ACCOUNT looked identical
            # to a missing button - and the run could not record the
            # restriction it had just been told about.
            return False, (getattr(self, "last_share_error", "")
                           or "Timeline share failed")
        step += 1

        if not await self._share_to_story():
            self.log("Story share skipped or failed (non-fatal)")
        step += 1

        # Navigate back to the post for reaction/comment (page may have moved after sharing)
        if reaction:
            self.log("Performing auto-reaction...")
            await self._auto_react(post_url, reaction)

        if comment_text and comment_text.strip():
            self.log("Performing auto-comment...")
            await self._auto_comment(post_url, comment_text)

        return True, "Posted to Timeline"

    # ── Post Text to Timeline ──────────────────────────────

    async def post_text_to_timeline(self, text: str, image_paths: list[str] | None = None) -> tuple[bool, str]:
        """Post a text status update to the user's Facebook Timeline.
        Optionally attaches one or more images.
        """
        self.log("Posting text to Timeline...")
        
        # Debug: Log what we received
        if image_paths:
            self.log(f"📎 Received {len(image_paths)} image path(s): {image_paths}")
        else:
            self.log("📎 No images provided (image_paths is None or empty)")

        # Navigate to Facebook homepage
        try:
            await self.page.goto("https://www.facebook.com/",
                                 timeout=30000, wait_until="load")
            await asyncio.sleep(random.uniform(2, 4))
        except Exception as e:
            return False, f"Failed to load Facebook: {e}"

        # Find the status composer ("What's on your mind?")
        self.log("Looking for status composer...")
        composer = await self._find(
            css=[
                'div[role="button"]:has-text("What\'s on your mind")',
                'div[role="button"]:has-text("what\'s on your mind")',
                '[aria-label*="What\'s on your mind" i]',
                '[aria-label*="what\'s on your mind" i]',
                '[aria-label*="create a post" i]',
                '[role="textbox"][aria-placeholder*="what" i]',
            ],
            timeout=15,
            visible_only=True,
        )
        if not composer:
            await self._dump_page_buttons("composer_not_found")
            return False, "Status composer not found on homepage"

        # Click composer using JS to properly trigger React
        self.log("Clicking status composer to expand...")
        await composer.scroll_into_view_if_needed()
        await asyncio.sleep(0.3)
        try:
            await composer.evaluate("el => el.click()")
        except Exception:
            await composer.click(force=True)

        # Wait for the expanded composer dialog to appear
        self.log("Waiting for expanded composer dialog...")
        for _ in range(15):
            await asyncio.sleep(0.5)
            dialog_open = await self.page.evaluate('''() => {
                // Check if there's a visible dialog that likely contains the composer
                // Facebook's expanded composer is role="dialog" containing contenteditable
                const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                    .filter(el => el.offsetParent !== null);
                for (const dlg of dialogs) {
                    const txt = (dlg.innerText || "").toLowerCase();
                    if (txt.includes("post") && dlg.querySelector('div[contenteditable="true"]'))
                        return true;
                }
                // Also check for expanded inline composer (non-dialog pattern)
                const editors = [...document.querySelectorAll(
                    'div[role="textbox"][contenteditable="true"]'
                )].filter(el => {
                    const r = el.getBoundingClientRect();
                    return el.offsetParent !== null && r.height > 100;
                });
                if (editors.length > 0) return true;
                return false;
            }''')
            if dialog_open:
                self.log("Expanded composer is open")
                break
        else:
            # Composer didn't expand — dump page for debugging
            await self._dump_page_buttons("composer_not_expanded")
            return False, "Status composer did not expand"
        await asyncio.sleep(1)

        # Find the text input area — prefer the one inside the expanded composer dialog
        self.log("Finding text area inside composer...")
        text_area = await self._find(
            css=[
                'div[role="textbox"][contenteditable="true"]:not([aria-hidden="true"])',
                'div[contenteditable="true"]:not([aria-hidden="true"])',
            ],
            timeout=8,
            visible_only=True,
            use_last=True,
        )
        if not text_area:
            await self._dump_page_buttons("text_area_not_found")
            return False, "Text input area not found in composer"

        # Click and type text using keyboard (React-compatible)
        self.log("Typing text into composer...")
        try:
            await text_area.evaluate("el => el.click()")
        except Exception:
            await text_area.click(force=True)
        await asyncio.sleep(0.3)
        await self.page.keyboard.type(text, delay=random.randint(40, 100))
        await asyncio.sleep(random.uniform(0.5, 1))

        # Verify text was actually entered
        try:
            text_verified = await self.page.evaluate(f'''() => {{
                const editors = [...document.querySelectorAll('div[role="textbox"][contenteditable="true"]')]
                    .filter(el => el.offsetParent !== null);
                for (const ed of editors) {{
                    const txt = (ed.innerText || ed.textContent || "").trim();
                    if (txt.includes({json.dumps(text[:30])})) return true;
                }}
                return false;
            }}''')
            if not text_verified:
                self.log("Warning: typed text not detected in any editable area")
        except Exception:
            pass

        # ── Upload images if provided ────────────────────────────────
        if image_paths:
            valid_paths = [p for p in image_paths if os.path.isfile(p)]
            skipped = [p for p in image_paths if not os.path.isfile(p)]
            for s in skipped:
                self.log(f"⚠️ Image file not found on disk: {s}, skipping")
            if not valid_paths:
                self.log("⚠️ No valid image files to upload")
            else:
                self.log(f"📷 Uploading {len(valid_paths)} image(s): {', '.join(Path(p).name for p in valid_paths)}")

                uploaded = False

                # Take baseline: count images near the editor/composer area
                baseline_img_count = await self.page.evaluate('''() => {
                    // Try dialog first
                    const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                        .filter(el => el.offsetParent !== null);
                    if (dialogs.length) {
                        return dialogs[dialogs.length - 1].querySelectorAll('img').length;
                    }
                    // Fallback: find the last visible editor and count sibling/nearby imgs
                    const editors = [...document.querySelectorAll(
                        'div[role="textbox"][contenteditable="true"], div[contenteditable="true"]'
                    )].filter(el => el.offsetParent !== null && el.getBoundingClientRect().height > 50);
                    if (editors.length) {
                        const editor = editors[editors.length - 1];
                        // Walk up to a reasonable container (up to 5 levels)
                        let container = editor;
                        for (let i = 0; i < 5 && container.parentElement; i++) {
                            container = container.parentElement;
                        }
                        return container.querySelectorAll('img').length;
                    }
                    return 0;
                }''')
                self.log(f"📊 Baseline images: {baseline_img_count}")

                # ── IMAGE UPLOAD (FILE CHOOSER METHOD - Click photo icon FIRST) ──
                self.log("📁 Uploading images via photo icon + file chooser...")
                
                try:
                    # Convert to absolute paths
                    abs_paths = [os.path.abspath(p) for p in valid_paths]
                    
                    # Click the photo icon in "Add to your post" section to trigger file chooser
                    self.log("  📷 Looking for photo/video icon...")
                    
                    # CRITICAL: Look for the photo icon by its aria-label first
                    photo_icon = await self._find(
                        css=[
                            # Standard Photo/video icon
                            '[role="dialog"] [aria-label="Photo/video"]',
                            '[role="dialog"] [aria-label*="Photo" i][aria-label*="video" i]',
                            # Filipino
                            '[role="dialog"] [aria-label*="Larawan" i]',
                            # Spanish/Portuguese  
                            '[role="dialog"] [aria-label*="Foto" i]',
                        ],
                        timeout=8,
                        visible_only=True,
                    )
                    
                    if not photo_icon:
                        self.log("  ⚠️ Standard photo icon not found, trying alternative selectors...")
                        # For Profile 6: Use multiple strategies to find the correct photo icon
                        photo_icon = await self.page.evaluate('''() => {
                            const dialog = [...document.querySelectorAll('[role="dialog"]')]
                                .filter(el => el.offsetParent !== null)[0];
                            if (!dialog) return null;
                            
                            // Get all buttons in the dialog
                            const icons = [...dialog.querySelectorAll('[role="button"]')];
                            
                            // Strategy 1: Find by SVG path shape (photo icon has specific path)
                            // Photo icon typically has rect elements or camera-like paths
                            for (const icon of icons) {
                                const ariaLabel = (icon.getAttribute('aria-label') || '').toLowerCase();
                                
                                // STRICT FILTERING: Skip known non-photo icons
                                if (ariaLabel.includes('tag')) continue;
                                if (ariaLabel.includes('feeling')) continue;
                                if (ariaLabel.includes('location')) continue;
                                if (ariaLabel.includes('check in')) continue;
                                if (ariaLabel.includes('gif')) continue;
                                if (ariaLabel.includes('activity')) continue;
                                
                                const svg = icon.querySelector('svg');
                                if (!svg) continue;
                                
                                // Check for image/photo related SVG structure
                                const paths = svg.querySelectorAll('path');
                                const rects = svg.querySelectorAll('rect');
                                const circles = svg.querySelectorAll('circle');
                                
                                // Photo icon typically has multiple shapes (camera/image structure)
                                if (paths.length >= 2 || rects.length >= 1) {
                                    // Further check: green color (photo icon color)
                                    const computedStyle = window.getComputedStyle(svg);
                                    const fill = svg.getAttribute('fill') || computedStyle.fill;
                                    const color = svg.getAttribute('color') || computedStyle.color;
                                    
                                    // Green shades: #45BD62, #2e7d32, #16a34a, rgb(69,189,98)
                                    const isGreen = (fill && (fill.includes('45') || fill.includes('bd') || fill.includes('2e') || fill.includes('16'))) ||
                                                   (color && (color.includes('45') || color.includes('bd') || color.includes('2e') || color.includes('16')));
                                    
                                    if (isGreen || ariaLabel === '') {
                                        icon.setAttribute('data-photo-icon-found', 'true');
                                        return true;
                                    }
                                }
                            }
                            
                            // Strategy 2: Find by input[type="file"] sibling/parent
                            // Photo upload buttons are often near hidden file inputs
                            const fileInputs = [...dialog.querySelectorAll('input[type="file"]')];
                            for (const input of fileInputs) {
                                const accept = input.getAttribute('accept') || '';
                                if (accept.includes('image')) {
                                    // Find nearest button
                                    let parent = input.parentElement;
                                    for (let i = 0; i < 10 && parent; i++) {
                                        const btn = parent.querySelector('[role="button"]');
                                        if (btn && !btn.getAttribute('data-photo-icon-found')) {
                                            const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                                            if (!ariaLabel.includes('tag') && !ariaLabel.includes('feeling')) {
                                                btn.setAttribute('data-photo-icon-found', 'true');
                                                return true;
                                            }
                                        }
                                        parent = parent.parentElement;
                                    }
                                }
                            }
                            
                            // Strategy 3: First button with SVG in toolbar (last resort)
                            // Find "Add to your post" section
                            const allText = [...dialog.querySelectorAll('*')];
                            const addSection = allText.find(el => {
                                const text = (el.innerText || el.textContent || '').trim();
                                return text === 'Add to your post' || text.includes('Idagdag sa iyong post');
                            });
                            
                            if (addSection) {
                                let container = addSection;
                                for (let i = 0; i < 3 && container; i++) {
                                    container = container.parentElement;
                                    if (container) {
                                        const buttons = [...container.querySelectorAll('[role="button"]')];
                                        // Get FIRST button with SVG
                                        for (const btn of buttons) {
                                            if (btn.querySelector('svg')) {
                                                const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                                                // Must NOT be tag/feeling/location
                                                if (!ariaLabel.includes('tag') && !ariaLabel.includes('feeling') && 
                                                    !ariaLabel.includes('location') && !ariaLabel.includes('gif')) {
                                                    btn.setAttribute('data-photo-icon-found', 'true');
                                                    return true;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            return null;
                        }''')
                        
                        if photo_icon:
                            photo_icon = await self.page.query_selector('[data-photo-icon-found="true"]')
                            if photo_icon:
                                self.log("  ✅ Found photo icon via alternative detection")
                    
                    if not photo_icon:
                        raise Exception("Could not find photo/video icon in composer")
                    
                    # Log which icon we found for debugging
                    icon_label = await photo_icon.get_attribute('aria-label')
                    icon_debug = await self.page.evaluate('''(el) => {
                        const svg = el.querySelector('svg');
                        return {
                            tag: el.tagName,
                            ariaLabel: el.getAttribute('aria-label'),
                            hasInput: !!el.querySelector('input[type="file"]'),
                            svgFill: svg ? (svg.getAttribute('fill') || window.getComputedStyle(svg).fill) : null,
                            text: (el.innerText || '').substring(0, 30)
                        };
                    }''', photo_icon)
                    self.log(f"  🔍 Icon details: {icon_debug}")
                    
                    # Verify it's NOT the Tag people icon
                    if icon_label and 'tag' in icon_label.lower():
                        raise Exception(f"Found wrong icon (Tag people): {icon_label}")
                    
                    self.log("  ✅ Found photo icon, clicking to open file chooser...")
                    
                    # Click and wait for file chooser dialog
                    async with self.page.expect_file_chooser(timeout=10000) as fc_info:
                        await photo_icon.click()
                        self.log("  ⏳ Waiting for file chooser dialog...")
                    
                    file_chooser = await fc_info.value
                    self.log(f"  📂 File chooser opened! Setting {len(abs_paths)} file(s)...")
                    
                    # Set files in the chooser
                    await file_chooser.set_files(abs_paths)
                    self.log(f"  ✅ Files set in file chooser!")
                    
                    # Wait for Facebook to process and show preview
                    await asyncio.sleep(4)
                    
                    # Verify upload by checking for Next button or image previews
                    self.log("  🔍 Verifying upload...")
                    for attempt in range(15):
                        await asyncio.sleep(1)
                        
                        # Check for Next button (strongest signal)
                        next_btn = await self.page.query_selector('[role="dialog"] [aria-label="Next"]')
                        
                        # Check for image count increase
                        img_count = await self.page.evaluate('''() => {
                            const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                                .filter(el => el.offsetParent !== null);
                            return dialogs.length ? dialogs[dialogs.length - 1].querySelectorAll('img').length : 0;
                        }''')
                        
                        # Check for preview containers
                        preview_count = await self.page.evaluate('''() => {
                            const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                                .filter(el => el.offsetParent !== null);
                            if (!dialogs.length) return 0;
                            return dialogs[dialogs.length - 1].querySelectorAll('[data-visualcompletion="media-vc-image"]').length;
                        }''')
                        
                        new_images = img_count - baseline_img_count
                        
                        if attempt <= 2 or attempt % 4 == 0:
                            self.log(f"  [{attempt+1}s] imgs={img_count} (Δ{new_images:+d}), previews={preview_count}, next_btn={next_btn is not None}")
                        
                        # Success if we see Next button OR new images OR preview containers
                        if next_btn or new_images > 0 or preview_count > 0:
                            self.log(f"✅ Image upload SUCCESS at {attempt+1}s!")
                            self.log(f"   Detected: next_btn={next_btn is not None}, imgs={img_count}, previews={preview_count}")
                            uploaded = True
                            break
                    
                    if not uploaded:
                        self.log("  ⚠️ Upload verification timed out after 15s")
                        
                except Exception as outer_e:
                    self.log(f"  ❌ Image upload failed: {outer_e}")
                    
                    # LAST RESORT: Try finding hidden file input directly
                    self.log("  🔄 Attempting fallback: direct file input method...")
                    try:
                        file_input = await self.page.query_selector('[role="dialog"] input[type="file"][accept*="image"]')
                        if file_input:
                            self.log("  ✅ Found file input, setting files directly...")
                            abs_paths = [os.path.abspath(p) for p in valid_paths]
                            await file_input.set_input_files(abs_paths)
                            await asyncio.sleep(3)
                            
                            # Verify
                            img_count = await self.page.evaluate('''() => {
                                const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                                    .filter(el => el.offsetParent !== null);
                                return dialogs.length ? dialogs[dialogs.length - 1].querySelectorAll('img').length : 0;
                            }''')
                            
                            if img_count > baseline_img_count:
                                self.log(f"  ✅ Fallback SUCCESS! Images uploaded: {img_count - baseline_img_count}")
                                uploaded = True
                            else:
                                self.log("  ⚠️ Fallback method did not upload images")
                        else:
                            self.log("  ⚠️ No file input found in composer")
                    except Exception as fallback_e:
                        self.log(f"  ❌ Fallback also failed: {fallback_e}")
                    
                    if not uploaded:
                        self.log(f"     Files will not be attached to this post")

                if uploaded:
                    self.log(f"📸 Image(s) successfully attached! Waiting 2s to finalize...")
                    await asyncio.sleep(2)
                else:
                    self.log("⚠️ ❌ Image upload FAILED - posting text only")
                    self.log("   (Check if Photo/video button exists in composer)")

        # IMPORTANT: When images are uploaded, Facebook often shows a "Next" button
        # Check for "Next" button BEFORE looking for "Post" button
        self.log("Checking for Next button (multi-step composer)...")
        next_btn = await self._find(
            css=[
                '[role="dialog"] div[role="button"]:has-text-is("Next")',
                '[role="dialog"] div[role="button"]:text-is("Next")',
                '[role="dialog"] [aria-label="Next"]',
            ],
            timeout=3,
            visible_only=True,
        )
        
        if next_btn:
            self.log("⚠️  Multi-step composer detected! Clicking 'Next' button first...")
            try:
                await next_btn.evaluate("el => el.click()")
                self.log("Next button clicked - waiting for Step 2 (Post screen)...")
                # CRITICAL: Wait longer for the second screen to fully load
                await asyncio.sleep(5)
                
                # Wait for the dialog to transition to the Post screen
                # The Post button should appear after the Next transition
                for wait_attempt in range(10):
                    await asyncio.sleep(1)
                    # Check if Post button is now visible
                    post_check = await self.page.query_selector('[role="dialog"] [aria-label="Post"]')
                    if post_check:
                        is_visible = await post_check.is_visible()
                        if is_visible:
                            self.log(f"✅ Post button appeared after {wait_attempt + 1}s")
                            break
                    if wait_attempt % 3 == 0:
                        self.log(f"  Waiting for Post button... ({wait_attempt + 1}s)")
                else:
                    self.log("⚠️ Post button still not visible after 10s, proceeding anyway...")
                    
            except Exception as e:
                self.log(f"Failed to click Next button: {e}")

        # Find the Post button — ONLY inside [role="dialog"] (expanded composer)
        # Using non-dialog-scoped selectors risks clicking the wrong button.
        self.log("Looking for Post button inside composer dialog...")
        
        # Try dialog-scoped selectors first, with MULTILINGUAL support
        # Support: English, Filipino/Tagalog, Spanish, French, Portuguese, etc.
        # Increased timeout to 20 seconds for slower Facebook loading (especially after Next button)
        post_btn = await self._find(
            css=self.COMPOSER_POST_SELECTORS,
            timeout=20,  # Increased from 15 to 20 seconds
            visible_only=True,
        )
        if post_btn:
            btn_info = await post_btn.evaluate('''el => ({
                tag: el.tagName, text: el.innerText.trim(),
                ariaLabel: el.getAttribute("aria-label"),
                disabled: el.hasAttribute("aria-disabled") ? el.getAttribute("aria-disabled") : null,
                className: el.className.substring(0, 100),
                parentDialog: !!el.closest('[role="dialog"]')
            })''')
            self.log(f"Post button found (dialog-scoped): {btn_info}")
            # Check if disabled
            if btn_info.get("disabled") == "true":
                self.log("⚠️ Post button is aria-disabled=true — waiting 5s and retrying...")
                await asyncio.sleep(5)
                # Re-check with longer timeout
                post_btn = await self._find(
                    css=[
                        '[role="dialog"] [aria-label="Post"]',
                        '[role="dialog"] div[role="button"]:has-text-is("Post")',
                        '[role="dialog"] div[role="button"]:text-is("Post")',
                    ],
                    timeout=15,  # Increased timeout
                    visible_only=True,
                )
                if post_btn:
                    btn_info = await post_btn.evaluate('''el => ({
                        disabled: el.hasAttribute("aria-disabled") ? el.getAttribute("aria-disabled") : null,
                    })''')
                    self.log(f"Post button re-check: {btn_info}")

        if not post_btn:
            # Last resort: try broader selectors with multilingual support
            self.log("Dialog-scoped Post button not found, trying broader selectors...")
            post_btn = await self._find(
                css=[
                    # English
                    '[aria-label="Post"]',
                    'div[role="button"]:has-text-is("Post")',
                    'div[role="button"]:text-is("Post")',
                    'button:has-text-is("Post")',
                    # Filipino
                    'div[role="button"]:has-text-is("I-post")',
                    'div[role="button"]:has-text-is("Mag-post")',
                    # Spanish
                    'div[role="button"]:has-text-is("Publicar")',
                    # French
                    'div[role="button"]:has-text-is("Publier")',
                    # Portuguese
                    'div[role="button"]:has-text-is("Postar")',
                ],
                timeout=10,
                visible_only=True,
            )
            if post_btn:
                btn_info = await post_btn.evaluate('''el => ({
                    tag: el.tagName, text: el.innerText.trim(),
                    ariaLabel: el.getAttribute("aria-label"),
                    parentDialog: !!el.closest('[role="dialog"]'),
                    parentClassName: el.parentElement ? el.parentElement.className.substring(0, 100) : ""
                })''')
                self.log(f"Post button found (non-dialog-scoped): {btn_info}")

        if not post_btn:
            # Final fallback: XPath with multilingual support
            self.log("Standard selectors failed, trying final fallback (XPath multilingual)...")
            try:
                post_btn = await self.page.wait_for_selector(
                    "xpath=//div[@role='button' and (contains(text(), 'Post') or contains(text(), 'I-post') or contains(text(), 'Mag-post') or contains(text(), 'Publicar') or contains(text(), 'Publier') or contains(text(), 'Postar'))] | //span[(contains(text(), 'Post') or contains(text(), 'I-post') or contains(text(), 'Publicar'))]/ancestor::div[@role='button'][1]",
                    timeout=10000,
                    state="visible"
                )
                if post_btn:
                    self.log("Post button found via XPath fallback!")
            except Exception as e:
                self.log(f"XPath fallback also failed: {e}")

        if not post_btn:
            await self._dump_page_buttons("post_btn_not_found")
            
            # FINAL WORKAROUND: Try keyboard shortcut Ctrl+Enter (posts in many Facebook UIs)
            self.log("Post button not found, trying keyboard shortcut (Ctrl+Enter)...")
            try:
                # Wait a moment for text to be ready
                await asyncio.sleep(1)
                # Try Ctrl+Enter shortcut to post
                await self.page.keyboard.press("Control+Enter")
                await asyncio.sleep(2)
                
                # Check if dialog closed (post went through)
                dialog_open = await self.page.locator('[role="dialog"]').count() > 0
                if not dialog_open:
                    self.log("✅ Keyboard shortcut worked! Dialog closed - post submitted")
                    return True, "Text posted to Timeline successfully (keyboard shortcut)"
                else:
                    self.log("⚠️  Dialog still open after keyboard shortcut")
                    return False, "Post button not found and keyboard shortcut failed"
            except Exception as e:
                self.log(f"❌ Keyboard shortcut failed: {e}")
                return False, "Post button not found"

        await post_btn.scroll_into_view_if_needed()
        await asyncio.sleep(0.3)

        # Use JavaScript native click for reliable React event handling
        try:
            await post_btn.evaluate("el => el.click()")
            self.log("Post button clicked via JavaScript")
        except Exception as e:
            self.log(f"JS click failed, trying Playwright click: {e}")
            await post_btn.click(force=True)

        # Wait for the post to be submitted
        await asyncio.sleep(random.uniform(2, 3))

        # Check for success/error toasts
        if not await self._verify_post_shared():
            return False, "Text post was rejected by Facebook"

        # Verify the expanded composer dialog closed — this is the key proof
        # that the post went through. If the dialog is still open, the post failed.
        self.log("Verifying composer dialog closed...")
        dialog_still_open = True
        for _ in range(10):
            await asyncio.sleep(0.5)
            try:
                dialog_still_open = await self.page.evaluate('''() => {
                    // Check if there's a visible dialog with composer-like content
                    const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                        .filter(el => el.offsetParent !== null);
                    for (const dlg of dialogs) {
                        const txt = (dlg.innerText || "").toLowerCase();
                        if ((txt.includes("post") || txt.includes("what's on your mind")) && 
                            dlg.querySelector('div[contenteditable="true"]'))
                            return true;
                    }
                    // Also check for inline expanded composer (non-dialog)
                    const editors = [...document.querySelectorAll(
                        'div[role="textbox"][contenteditable="true"], div[contenteditable="true"]'
                    )].filter(el => el.offsetParent !== null && el.getBoundingClientRect().height > 100);
                    if (editors.length > 0) return true;
                    return false;
                }''')
                if not dialog_still_open:
                    self.log("Composer dialog closed — post was submitted")
                    break
            except Exception:
                break

        if dialog_still_open:
            # Diagnostic: dump all visible dialogs and their contents
            diag_info = await self.page.evaluate('''() => {
                const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                    .filter(el => el.offsetParent !== null);
                return dialogs.map(d => ({
                    text: (d.innerText || '').substring(0, 300),
                    hasEditor: !!d.querySelector('div[contenteditable="true"]'),
                    hasPostBtn: !!d.querySelector('[aria-label="Post"]')
                }));
            }''')
            self.log(f"Open dialogs at failure: {diag_info}")

            # Check if Facebook is blocking with a rate-limit or content warning
            diag_texts = " ".join(d.get("text", "").lower() for d in diag_info)
            rate_limited = any(kw in diag_texts for kw in [
                "limit how often", "too many", "slow down", "try again later",
                "spam", "blocked", "restrict", "rate limit",
            ])
            content_blocked = any(kw in diag_texts for kw in [
                "can't be combined", "can't post", "violates", "not allowed",
                "against our standards", "removed",
            ])

            if rate_limited:
                self.log("⛔ Facebook rate limit detected — too many posts too quickly")
                self._post_failed = True
                await self._dump_page_buttons("rate_limited")
                return False, "Rate limited by Facebook — posting too frequently"

            if content_blocked:
                self.log("⛔ Facebook content block detected")
                self._post_failed = True
                await self._dump_page_buttons("content_blocked")
                return False, "Post rejected by Facebook — content policy violation"

            # Try Ctrl+Enter keyboard shortcut as fallback
            self.log("Composer still open, trying Ctrl+Enter keyboard shortcut...")
            try:
                await self.page.keyboard.press("Control+Enter")
                await asyncio.sleep(random.uniform(3, 4))
                dialog_still_open = await self.page.evaluate('''() => {
                    const dialogs = [...document.querySelectorAll('[role="dialog"]')]
                        .filter(el => el.offsetParent !== null);
                    for (const dlg of dialogs) {
                        const txt = (dlg.innerText || "").toLowerCase();
                        if ((txt.includes("post") || txt.includes("what's on your mind")) &&
                            dlg.querySelector('div[contenteditable="true"]'))
                            return true;
                    }
                    return false;
                }''')
            except Exception:
                pass

        if dialog_still_open:
            await self._dump_page_buttons("post_failed")
            return False, "Composer dialog did not close — post was not submitted"

        # ── Confirm the post appears in the feed ─────────────────
        # Scan the news feed for article elements containing our text.
        # This is a best-effort check — if the text is found, great.
        # If not, we still return success since the dialog closed and
        # no error was detected. Facebook may not show our own post
        # in the news feed immediately.
        self.log("Verifying post appears in the feed...")
        await asyncio.sleep(2)
        post_found = False
        try:
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            for attempt in range(5):
                post_found = await self.page.evaluate(f'''() => {{
                    const articles = [...document.querySelectorAll('[role="article"]')];
                    const search = {json.dumps(text[:60].lower())};
                    for (const article of articles) {{
                        const txt = (article.innerText || "").toLowerCase();
                        if (txt.includes(search)) return true;
                    }}
                    return false;
                }}''')
                if post_found:
                    break
                await self.page.evaluate("window.scrollBy(0, 300)")
                await asyncio.sleep(1.5)
        except Exception:
            pass

        if post_found:
            self.log("Post confirmed in feed!")
        else:
            # Try the profile page as a fallback
            try:
                await self.page.goto("https://www.facebook.com/me",
                                     timeout=15000, wait_until="domcontentloaded")
                await asyncio.sleep(3)
                for _ in range(5):
                    post_found = await self.page.evaluate(f'''() => {{
                        const articles = [...document.querySelectorAll('[role="article"]')];
                        const search = {json.dumps(text[:60].lower())};
                        for (const article of articles) {{
                            const txt = (article.innerText || "").toLowerCase();
                            if (txt.includes(search)) return true;
                        }}
                        return false;
                    }}''')
                    if post_found:
                        break
                    await self.page.evaluate("window.scrollBy(0, 400)")
                    await asyncio.sleep(2)
            except Exception:
                pass

            if post_found:
                self.log("Post confirmed on profile page!")
            else:
                self.log("Post not found in feed (non-fatal — post likely went through)")

        self.log("Text posted to Timeline successfully!")
        return True, "Text posted to Timeline"

    async def share_post_to_group(self, post_url: str, group_name: str,
                                    comment_text: str | None = None,
                                    reaction: str | None = None,
                                    skip_timeline: bool = False,
                                    skip_reaction: bool = False) -> tuple[bool, str]:
        step = 1

        # Normalize Facebook URL to full format
        if post_url and not post_url.startswith("http"):
            post_url = f"https://www.facebook.com/{post_url}"

        # Convert mobile URLs to desktop URLs
        if post_url:
            post_url = post_url.replace("m.facebook.com", "www.facebook.com")
            post_url = post_url.replace("mobile.facebook.com", "www.facebook.com")

        # Extract the post/video ID from the URL for precise targeting
        self._target_post_id = None
        if post_url:
            m = re.search(r'/(?:videos?|posts?|photos?|reels?)/(\d+)', post_url)
            if m:
                self._target_post_id = m.group(1)
            else:
                m = re.search(r'[?&](?:id|story_fbid)=(\d+)', post_url)
                if m:
                    self._target_post_id = m.group(1)
        if self._target_post_id:
            self.log(f"   Target post/video ID: {self._target_post_id}")

        self.log(f"[{step}] Navigating to post URL...")
        for attempt in range(3):
            try:
                await self.page.goto(post_url, timeout=30000, wait_until="load")
                await asyncio.sleep(random.uniform(2, 4))
                break
            except Exception as e:
                err = str(e)
                if "interrupted by another navigation" in err and attempt < 2:
                    self.log(f"Navigation interrupted (attempt {attempt+1}), retrying in 3s...")
                    await asyncio.sleep(3)
                    continue
                return False, f"Failed to load post URL: {err}"
        step += 1

        # ── Identify the post container ──────────────────────
        post = self.page.locator('[role="article"]').first
        if await post.count() == 0:
            self.log("Post container [role=article] not found, searching whole page")
            post = self.page
        else:
            self.log("Found post container")

        # Check if this is the user's own post (can't share your own posts)
        is_own_post = await self.page.evaluate("""() => {
            const buttons = [...document.querySelectorAll('[role="button"]')];
            for (const btn of buttons) {
                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                const text = (btn.innerText || '').toLowerCase();
                if (aria.includes('edit post') || text.includes('edit post') ||
                    (aria === 'edit' && btn.offsetParent !== null)) {
                    return true;
                }
            }
            const menuItems = [...document.querySelectorAll('*')];
            for (const item of menuItems) {
                const text = (item.innerText || item.textContent || '').toLowerCase();
                if (text.includes('turn on notifications for this post') ||
                    text.includes('save post')) {
                    return true;
                }
            }
            return false;
        }""")
        if is_own_post:
            self.log("This appears to be your own post - cannot share your own posts")
            return False, "Cannot share your own post"

        self.log("Scrolling to reveal action buttons...")
        await self._debug_dump("group_before_share")
        await self.page.evaluate("""(targetId) => {
            const dlg = document.querySelector('[role="dialog"]');
            if (dlg) dlg.scrollBy(0, 600);
            else {
                // Try to find and scroll to the target article
                const articles = [...document.querySelectorAll('[role="article"]')];
                let target = null;
                if (targetId) {
                    for (const art of articles) {
                        if ((art.innerHTML || '').includes(targetId)) {
                            target = art;
                            break;
                        }
                    }
                }
                if (!target && articles.length > 0) target = articles[0];
                if (target) {
                    target.scrollIntoView({behavior: 'smooth', block: 'center'});
                } else {
                    document.documentElement.scrollBy(0, 600);
                }
            }
        }""", self._target_post_id)
        await asyncio.sleep(0.5)

        # ── Share to Timeline + Story (once only, skip in bulk after first) ──
        if skip_timeline:
            self.log("Skipping timeline/story share (already done)")
        else:
            timeline_ok = await self._share_to_timeline()
            if not timeline_ok:
                self.log("Timeline share skipped or failed (non-fatal, continuing to group)")
            step += 1

            story_ok = await self._share_to_story()
            if not story_ok:
                self.log("Story share skipped or failed (non-fatal, continuing to group)")
            step += 1

        # ── Share to Group ──
        # Get delay settings to avoid spam detection
        delays = cfg.get_share_delays()
        
        self.log(f"[{step}] Sharing to Group...")
        if not await self._click_share_button():
            return False, "Share button not found"
        
        # Add delay after clicking Share button (human-like behavior)
        delay_after_button = random.uniform(
            delays["after_share_button_min"], 
            delays["after_share_button_max"]
        )
        self.log(f"Waiting {delay_after_button:.1f}s after Share button...")
        await asyncio.sleep(delay_after_button)
        
        if not await self._pick_option_in_modal("Group"):
            return False, "'Share to a Group' option not found"
        step += 1

        self.log(f"[{step}] Searching for group '{group_name}'...")
        share_dialog = self.page.locator('[role="dialog"]:visible').last
        try:
            search_el = await self._find(
                css=[
                    "input[placeholder*='search' i]",
                    "input[role='combobox']",
                ],
                label="Search for groups",
                timeout=10,
                parent=share_dialog,
                visible_only=True,
            )
            if not search_el:
                return False, "Group search input not found"
            await search_el.scroll_into_view_if_needed()
            await search_el.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await search_el.fill("")
            await self.page.keyboard.type(group_name, delay=random.randint(50, 120))
            await asyncio.sleep(random.uniform(2, 3))
        except Exception as e:
            return False, f"Could not find group search input: {e}"
        step += 1

        self.log(f"[{step}] Selecting first search result...")
        try:
            deadline = time.monotonic() + 10
            first_result = None
            while time.monotonic() < deadline and first_result is None:
                for sel in (
                    f'[role="button"]:has-text("{group_name}")',
                    f'a:has-text("{group_name}")',
                    f'[role="link"]:has-text("{group_name}")',
                    'a[href*="/groups/"]',
                    '[role="option"]',
                    '[role="menuitem"]',
                ):
                    loc = share_dialog.locator(sel).first
                    try:
                        if await loc.count() > 0 and await loc.is_visible():
                            first_result = loc
                            break
                    except Exception:
                        continue
                if not first_result:
                    await asyncio.sleep(0.3)

            if not first_result:
                return False, f"No group found matching '{group_name}'"

            group_found = group_name
            try:
                t = await first_result.inner_text()
                if t and t.strip():
                    group_found = t.strip()
            except Exception:
                pass

            await first_result.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.3, 0.7))
            await first_result.click(force=True)
            await asyncio.sleep(random.uniform(2, 3))
        except Exception as e:
            return False, f"No group found matching '{group_name}': {e}"
        step += 1

        self.log(f"[{step}] Clicking Post button...")
        try:
            # Diagnostic: dump all visible dialogs
            try:
                dialogs = self.page.locator('[role="dialog"]:visible')
                dc = await dialogs.count()
                self.log(f"Visible dialogs: {dc}")
                for i in range(dc):
                    txt = (await dialogs.nth(i).inner_text() or "")[:200]
                    self.log(f"  Dialog {i}: {txt.strip()}")
            except Exception:
                pass

            # Phase 1: global exact text/aria-label match (lowercased)
            clicked = await self.page.evaluate('''
                () => {
                    const labels = ["post", "share", "done", "publish"];
                    const buttons = [...document.querySelectorAll('[role="button"], button, input[type="submit"]')];
                    for (const label of labels) {
                        const found = buttons.find(el => {
                            const t = (el.innerText || "").trim().toLowerCase();
                            const a = (el.getAttribute("aria-label") || "").trim().toLowerCase();
                            return t === label || a === label;
                        });
                        if (found && !found.disabled && found.getAttribute("aria-disabled") !== "true" && found.offsetParent !== null) {
                            found.click();
                            return true;
                        }
                    }
                    return false;
                }
            ''')

            # Phase 2: Y-position fallback (bottom-most visible, not back/close)
            if not clicked:
                await self.page.evaluate("document.querySelector('[role=\"dialog\"]:visible')?.scrollTo(0, 1e9)")
                await asyncio.sleep(0.5)
                clicked = await self.page.evaluate('''
                    () => {
                        const buttons = [...document.querySelectorAll('[role="button"], button, input[type="submit"]')]
                            .filter(el => {
                                const rect = el.getBoundingClientRect();
                                const t = (el.innerText || "").trim().toLowerCase();
                                const a = (el.getAttribute("aria-label") || "").trim().toLowerCase();
                                return el.offsetParent !== null
                                    && rect.width > 50 && rect.height > 20
                                    && t !== "back" && t !== "close"
                                    && a !== "back" && a !== "close"
                                    && !el.disabled && el.getAttribute("aria-disabled") !== "true";
                            })
                            .sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top);
                        if (buttons.length) { buttons[0].click(); return true; }
                        return false;
                    }
                ''')

            if not clicked:
                try:
                    items = await self.page.evaluate('''
                        () => {
                            const buttons = [...document.querySelectorAll('[role="button"], button, input[type="submit"]')]
                                .filter(el => el.offsetParent !== null);
                            return buttons.map(n => ({
                                text: (n.innerText || "").trim(),
                                aria: n.getAttribute("aria-label")
                            }));
                        }
                    ''')
                    self.log("Post button not found. Visible buttons:")
                    for b in items:
                        self.log(f"  [{b['aria']}] {b['text']}")
                except Exception:
                    pass
                return False, "Post button not found"

            await asyncio.sleep(1)
        except Exception as e:
            return False, f"Could not click Post button: {e}"
        step += 1

        # Use configurable delay after posting (longer to avoid spam detection)
        delay = random.uniform(delays["after_post_min"], delays["after_post_max"])
        self.log(f"Waiting {delay:.1f}s for post to complete...")
        await asyncio.sleep(delay)

        if skip_reaction:
            self.log("Skipping reaction/comment (already done)")
        else:
            if reaction:
                self.log("Performing auto-reaction...")
                await self._auto_react(post_url, reaction)

            if comment_text and comment_text.strip():
                self.log("Performing auto-comment...")
                await self._auto_comment(post_url, comment_text)

        return True, f"Shared to '{group_found}'"

    # ── Join Group ─────────────────────────────────────────────

    async def fetch_my_groups(self) -> list[dict]:
        """Fetch the list of groups this profile belongs to.

        Navigates to the Facebook Groups sidebar page, scrolls to load
        all groups, then extracts names and URLs via JS DOM scraping.

        Returns:
            List of dicts: [{"name": "Group Name", "url": "https://..."}, ...]
        """
        self.log("Fetching my groups...")

        if not self.page:
            return []

        groups = []

        try:
            await self.page.goto(
                "https://www.facebook.com/groups/?feed_type=group_post",
                timeout=45000,
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(3)

            # Scroll down several times to load more groups in the sidebar
            for _ in range(10):
                await self.page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(1.5)

            # Extract groups from the left sidebar / group list page
            raw = await self.page.evaluate("""() => {
                const results = [];
                const seen = new Set();

                // Method 1: Look for group links in sidebar and main content
                const links = document.querySelectorAll('a[href*="/groups/"]');
                for (const link of links) {
                    const href = link.href || '';
                    const match = href.match(/facebook\\.com\\/groups\\/([^/?]+)/);
                    if (!match) continue;
                    const slug = match[1];
                    if (seen.has(slug)) continue;
                    seen.add(slug);

                    // Get the visible text (group name)
                    let name = '';
                    // Try aria-label first
                    if (link.getAttribute('aria-label')) {
                        name = link.getAttribute('aria-label').trim();
                    }
                    // Try inner span/text
                    if (!name) {
                        const span = link.querySelector('span');
                        if (span) name = span.textContent.trim();
                    }
                    // Fallback to link text
                    if (!name) {
                        name = link.textContent.trim();
                    }
                    // Skip navigation-only links
                    if (!name || name.length < 2 || name === 'Groups' || name === 'See all groups') continue;

                    results.push({
                        name: name,
                        url: 'https://www.facebook.com/groups/' + slug + '/',
                    });
                }
                return results;
            }""")

            for item in (raw or []):
                name = (item.get("name") or "").strip()
                url = (item.get("url") or "").strip()
                if name and url:
                    groups.append({"name": name, "url": url})

            self.log(f"Found {len(groups)} group(s)")
            return groups

        except Exception as e:
            self.log(f"Error fetching groups: {e}")
            return groups

    async def join_group(self, group_url: str, max_retries: int = 2) -> tuple[bool, str]:
        """Navigate to a Facebook group and click the Join button.

        Args:
            group_url: Full Facebook group URL
                       (e.g. https://www.facebook.com/groups/groupname)
            max_retries: Number of retries on timeout/network errors.

        Returns:
            (ok, message) tuple.
        """
        self.log(f"Joining group: {group_url}")

        if not self.page:
            return False, "No page available"

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                timeout = 45000 if attempt == 0 else 60000
                await self.page.goto(group_url, timeout=timeout,
                                     wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(3, 5))

                # Check if already a member
                already = await self._find(
                    css=[
                        '[role="button"]:has-text("Joined")',
                        '[role="button"]:has-text("Member")',
                        '[aria-label="Joined"]',
                    ],
                    timeout=3,
                    visible_only=True,
                )
                if already:
                    txt = (await already.inner_text()).strip().lower()
                    if "joined" in txt or "member" in txt:
                        return True, "Already a member of this group"

                # Find and click the Join button
                join_btn = await self._find(
                    css=[
                        '[role="button"]:has-text("Join Group")',
                        '[role="button"]:has-text("Join")',
                    ],
                    text="Join Group",
                    timeout=10,
                    visible_only=True,
                )

                if not join_btn:
                    # Try aria-label fallback
                    join_btn = await self._find(
                        label="Join Group",
                        timeout=3,
                        visible_only=True,
                    )

                if not join_btn:
                    # Check for "Answer Questions" (some groups require this)
                    answer_btn = await self._find(
                        css=['[role="button"]:has-text("Answer")'],
                        timeout=3,
                        visible_only=True,
                    )
                    if answer_btn:
                        return False, ("This group requires you to answer "
                                       "questions before joining")
                    return False, "Join button not found"

                await join_btn.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.5, 1.0))
                await join_btn.click(force=True)
                await asyncio.sleep(random.uniform(3, 5))

                # Handle possible confirmation dialog
                confirm_btn = await self._find(
                    css=[
                        '[role="dialog"] [role="button"]:has-text("Join")',
                        '[role="dialog"] [role="button"]:has-text("Submit")',
                        '[role="dialog"] [role="button"]:has-text("Confirm")',
                    ],
                    timeout=3,
                    visible_only=True,
                )
                if confirm_btn:
                    await confirm_btn.click(force=True)
                    await asyncio.sleep(random.uniform(2, 4))

                # Verify result
                joined = await self._find(
                    css=[
                        '[role="button"]:has-text("Joined")',
                        '[role="button"]:has-text("Pending")',
                        '[role="button"]:has-text("Requested")',
                    ],
                    timeout=5,
                    visible_only=True,
                )
                if joined:
                    status = (await joined.inner_text()).strip()
                    if "pending" in status.lower() or "requested" in status.lower():
                        return True, "Join request sent — pending approval"
                    return True, "Successfully joined group"

                return True, "Join request sent"

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_timeout = "timeout" in err_str or "timed out" in err_str
                is_network = any(kw in err_str for kw in ["network", "connection", "navigate", "goto"])

                if (is_timeout or is_network) and attempt < max_retries:
                    wait = (attempt + 1) * 15
                    self.log(f"  Timeout on attempt {attempt+1}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    try:
                        await self.page.reload(timeout=30000, wait_until="commit")
                    except Exception:
                        pass
                    continue

                self.log(f"Error joining group: {e}")
                return False, f"Error joining group: {e}"

        return False, f"Error joining group: {last_error}"
