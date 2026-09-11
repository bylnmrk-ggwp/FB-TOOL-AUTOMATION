"""
Diagnose the live-watch feature: does a watch page actually play the video?

The Watch button logs "watching '<name>'" as soon as page.goto() returns, which
proves only that a document loaded - not that the account is logged in, not that
the page has a player, and not that anything is playing. This script reproduces
one watch page with the same browser mode, launch flags, viewport and storage
state, then reports the facts the app never checks:

    final URL after Facebook's redirects, login-gate verdict, <video> presence,
    readyState / paused / muted / currentTime sampled over time, page
    visibilityState, and any console errors.

Usage:
    python scripts/watch_diagnose.py <url>
    python scripts/watch_diagnose.py <url> "profile name"
    python scripts/watch_diagnose.py <url> --visible
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # scripts/
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.async_api import async_playwright

from src.storage import config_manager as cfg
from src.storage import database as db
from src.storage import state_cache

# When to sample the player, in seconds since navigation.
SAMPLE_AT = (3, 8, 15, 30, 60)

PROBE_JS = """() => {
    const vids = [...document.querySelectorAll('video')];
    const iframes = [...document.querySelectorAll('iframe')].map(f => f.src || '(srcdoc)');
    const v = vids[0];
    return {
        url: location.href,
        title: document.title,
        visibility: document.visibilityState,
        hasFocus: document.hasFocus(),
        videoCount: vids.length,
        iframeCount: iframes.length,
        iframes: iframes.slice(0, 5),
        video: v ? {
            paused: v.paused,
            ended: v.ended,
            muted: v.muted,
            volume: v.volume,
            readyState: v.readyState,
            networkState: v.networkState,
            currentTime: v.currentTime,
            duration: v.duration,
            width: v.videoWidth,
            height: v.videoHeight,
            error: v.error ? v.error.code : null,
            rectW: v.getBoundingClientRect().width,
            rectH: v.getBoundingClientRect().height,
        } : null,
        bodyText: (document.body ? document.body.innerText : '').slice(0, 300),
    };
}"""


async def main(url: str, profile: str | None, visible: bool) -> int:
    from src.core.facebook_automation import (FacebookAutomation, CHROME_PATH,
                                              MEMORY_FLAGS, SMALL_VIEWPORT,
                                              LOGIN_GATE_JS)

    ok = db.logged_in_profiles()
    profiles = [p for p in cfg.list_profiles() if p in ok]
    if profile:
        if profile not in cfg.list_profiles():
            print(f"No such profile: {profile}")
            return 1
        profiles = [profile]
    if not profiles:
        print("No active (logged-in) profiles.")
        return 1
    name = profiles[0]

    print("=" * 72)
    print(f"WATCH DIAGNOSTIC - profile '{name}'")
    print(f"URL: {url}")
    print("=" * 72)

    state = state_cache.load_state(name)
    source = "cache"
    if state is None:
        source = "live extract"
        base_path = cfg.get_profile_path(name)
        if not base_path:
            print("Profile has no Brave path and no cached state.")
            return 1
        temp = FacebookAutomation(log_callback=lambda m: print(f"   {m}"))
        try:
            state = await temp.extract_storage_state(base_path, skip_navigation=True)
        finally:
            try:
                await temp.quit()
            except Exception:
                pass
    if not state:
        print("No usable storage state - watch would skip this profile.")
        return 1

    cookies = {c.get("name") for c in state.get("cookies", [])}
    print(f"storage state: {source}, {len(state.get('cookies', []))} cookies, "
          f"c_user={'c_user' in cookies}, xs={'xs' in cookies}")

    mode = "visible" if visible else cfg.get_setting("browser_mode", "headless_new")
    args = [f"--window-size={SMALL_VIEWPORT['width']},{SMALL_VIEWPORT['height']}",
            *MEMORY_FLAGS, "--autoplay-policy=no-user-gesture-required"]
    launch_headless = False
    if mode == "headless_new":
        args.append("--headless=new")
    elif mode == "headless":
        launch_headless = True
    print(f"browser mode: {mode} (playwright headless={launch_headless})")
    print("-" * 72)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(executable_path=CHROME_PATH,
                                       headless=launch_headless, args=args)
    context = await browser.new_context(storage_state=state,
                                        viewport=SMALL_VIEWPORT, no_viewport=False)
    page = await context.new_page()

    console: list[str] = []

    def _on_console(msg):
        if msg.type in ("error", "warning"):
            console.append(f"{msg.type}: {msg.text[:200]}")

    page.on("console", _on_console)
    page.on("pageerror", lambda e: console.append(f"pageerror: {str(e)[:200]}"))

    # Deliberately no page.route() here: this run shows what the page does with
    # nothing intercepted, so a later run with blocking on isolates that cost.
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        print(f"goto status: {resp.status if resp else 'n/a'}")
    except Exception as e:
        print(f"navigation failed: {e}")

    try:
        gate = await page.evaluate(LOGIN_GATE_JS)
        print(f"login gate present: {gate}")
    except Exception as e:
        print(f"login-gate probe failed: {e}")

    prev = 0.0
    for i, t in enumerate(SAMPLE_AT):
        await asyncio.sleep(t - (SAMPLE_AT[i - 1] if i else 0))
        try:
            r = await page.evaluate(PROBE_JS)
        except Exception as e:
            print(f"t={t:>3}s  probe failed: {e}")
            continue
        print(f"t={t:>3}s  url={r['url'][:70]}")
        print(f"        visibility={r['visibility']} focus={r['hasFocus']} "
              f"videos={r['videoCount']} iframes={r['iframeCount']}")
        v = r["video"]
        if v:
            advanced = v["currentTime"] - prev
            prev = v["currentTime"]
            print(f"        video paused={v['paused']} ended={v['ended']} "
                  f"muted={v['muted']} vol={v['volume']} ready={v['readyState']} "
                  f"net={v['networkState']} err={v['error']}")
            print(f"        currentTime={v['currentTime']:.2f} (+{advanced:.2f}s) "
                  f"duration={v['duration']} size={v['width']}x{v['height']} "
                  f"box={v['rectW']:.0f}x{v['rectH']:.0f}")
        else:
            print(f"        NO <video>. body: {r['bodyText'][:160]!r}")

    print("-" * 72)
    if console:
        print(f"console ({len(console)} entries, first 15):")
        for line in console[:15]:
            print(f"   {line}")
    else:
        print("console: clean")

    try:
        await page.screenshot(path="watch_diagnose.png")
        print("screenshot: watch_diagnose.png")
    except Exception as e:
        print(f"screenshot failed: {e}")

    await context.close()
    await browser.close()
    await pw.stop()
    return 0


if __name__ == "__main__":
    argv = list(sys.argv[1:])
    vis = "--visible" in argv
    argv = [a for a in argv if a != "--visible"]
    if not argv:
        print(__doc__)
        sys.exit(1)
    sys.exit(asyncio.run(main(argv[0], argv[1] if len(argv) > 1 else None, vis)))
