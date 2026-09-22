"""A login form nobody can see does not mean the session is dead.

Facebook ships markup for a login form on pages a logged-in account is
perfectly entitled to read - a /share/p/ permalink opened over the feed is
the usual one. The nodes are in the DOM and hidden. LOGIN_GATE_JS has always
known this and tests every candidate with a visibility check before calling
it a gate.

`_is_logged_in` did not: it counted `input[name="email"]` with
locator.count(), which counts hidden nodes just the same, and so spent its
whole timeout deciding a live account was logged out. `_classify_account_access`
was supposed to be the second opinion that rescued those accounts, but it
repeated the identical unguarded count, so it agreed every time.

Measured on a 175-item comment run: of 53 accounts it called "logged out or
session expired", 9 reached their Facebook home page fine when re-checked
one at a time. Those 9 were marked not-logged-in, had their cached session
dropped, and were queued for a re-login they did not need.

Both checks must ask the visible DOM, and a control page with a REAL login
form must still read as logged out - the fix is "ignore what is hidden",
never "answer yes".
"""
import asyncio
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("hidden login form is not a logout")  # noqa: F821

from playwright.async_api import async_playwright  # noqa: E402

from src.core.facebook_automation import FacebookAutomation  # noqa: E402

# A post page a logged-in account can read. The login markup is present and
# hidden, exactly as Facebook serves it.
LOGGED_IN_PAGE = """<!doctype html><html><body>
  <div role="banner">Facebook</div>
  <div role="article">A post, readable because the session is live.</div>
  <div aria-label="Create a post">What's on your mind?</div>
  <div style="display:none">
    <form><input name="email"><input name="pass" type="password"></form>
  </div>
</body></html>"""

# The control: a real gate, visible, which must still read as logged out.
LOGGED_OUT_PAGE = """<!doctype html><html><body>
  <form><input name="email"><input name="pass" type="password"></form>
  <button>Log in</button>
</body></html>"""

URL = "https://www.facebook.com/share/p/proof/"


async def verdicts(html):
    """(_is_logged_in, _classify_account_access) for a page serving `html`."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    try:
        page = await (await browser.new_context()).new_page()
        await page.route("**/*", lambda route: asyncio.ensure_future(
            route.fulfill(status=200, content_type="text/html", body=html)))
        await page.goto(URL, wait_until="domcontentloaded")
        auto = FacebookAutomation(log_callback=lambda *a, **k: None)
        auto.page = page
        return (await auto._is_logged_in(timeout=3),
                await auto._classify_account_access())
    finally:
        await browser.close()
        await pw.stop()


async def classify_other_page(target_html, self_page_html):
    """_classify_account_access(page=...) must judge the page it was given.

    The login scan hands the classifier its own persistent-context page while
    self.page is something else entirely. Every test in the classifier reads
    `target` for that reason - except the live-session fast path, which asked
    self.page and so answered about the wrong tab.
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    try:
        context = await browser.new_context()
        target = await context.new_page()
        await target.route("**/*", lambda route: asyncio.ensure_future(
            route.fulfill(status=200, content_type="text/html", body=target_html)))
        await target.goto(URL, wait_until="domcontentloaded")

        other = await context.new_page()
        await other.route("**/*", lambda route: asyncio.ensure_future(
            route.fulfill(status=200, content_type="text/html", body=self_page_html)))
        await other.goto(URL, wait_until="domcontentloaded")

        auto = FacebookAutomation(log_callback=lambda *a, **k: None)
        auto.page = other
        return await auto._classify_account_access(page=target)
    finally:
        await browser.close()
        await pw.stop()


async def main():
    live_logged_in, live_status = await verdicts(LOGGED_IN_PAGE)
    if not live_logged_in:
        failures.append("hidden login form: _is_logged_in called a live session "  # noqa: F821
                        "logged out because of a hidden input")
    if live_status != FacebookAutomation.LOGGED_IN:
        failures.append(f"hidden login form: _classify_account_access said "  # noqa: F821
                        f"{live_status!r} about a live session, so the second "
                        f"opinion repeats the same mistake")

    # The control must not have been loosened into always saying yes.
    gated_logged_in, gated_status = await verdicts(LOGGED_OUT_PAGE)
    if gated_logged_in:
        failures.append("visible login form: _is_logged_in called a real login "  # noqa: F821
                        "page a live session")
    if gated_status != "logged_out_or_session_expired":
        failures.append(f"visible login form: _classify_account_access said "  # noqa: F821
                        f"{gated_status!r}, expected logged_out_or_session_expired")

    # The classifier must answer about the page it was handed, not self.page.
    handed = await classify_other_page(LOGGED_IN_PAGE, LOGGED_OUT_PAGE)
    if handed != FacebookAutomation.LOGGED_IN:
        failures.append(f"classifier judged the wrong page: asked about a live "  # noqa: F821
                        f"session it said {handed!r}, because the live-session "
                        f"check read self.page instead of the page argument")


asyncio.run(main())
