#!/usr/bin/env python3
"""
LOVE REACTION TEST HARNESS
==========================
Runs the 'love' reaction through the EXACT same code path as the app's
react-only batch flow (extract_storage_state -> shared browser ->
_auto_react), so we can verify the picker fix.

USAGE:
    python test_love_react.py "<post_url>" [profile1 profile2 profile3]

EXAMPLE:
    python test_love_react.py "https://www.facebook.com/share/p/1BwFv5EEnv/" revikahwinterky yeiriwinterky leilaanelisebc

IMPORTANT:
    Use a FRESH post URL that these profiles have NOT reacted to yet.
    If a profile already reacted (even the old Like fallback), _auto_react
    short-circuits with "Already reacted" and the fixed picker path is
    never exercised.

WHAT TO LOOK FOR IN THE OUTPUT:
    ✅ "Clicked emoji at clear point (scan 1)"   <- picker fix worked (trusted press)
    ✅ "Reacted with 'love'"                       <- reaction confirmed
    ❌ "point covered at press time"               <- still overlapped (bad)
    ❌ "Could not apply 'love', clicking Like as fallback"  <- still broken
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from playwright.async_api import async_playwright

from src.core.facebook_automation import (
    CHROME_PATH,
    MEMORY_FLAGS,
    SMALL_VIEWPORT,
    FacebookAutomation,
)
from src.storage import config_manager as cfg

DEFAULT_PROFILES = ["revikahwinterky", "yeiriwinterky", "leilaanelisebc"]


def _log(msg: str):
    print(msg, flush=True)


async def _extract_state(name: str) -> dict | None:
    """Mirror Phase 1 of _do_batch: extract storage state for one profile."""
    brave_path = cfg.get_profile_path(name)
    if not brave_path:
        _log(f"  ❌ Profile '{name}' not found in config — skipping")
        return None
    _log(f"  Extracting '{name}'...")
    auto = FacebookAutomation(log_callback=lambda m: _log(f"    {m}"))
    try:
        state = await auto.extract_storage_state(brave_path)
    finally:
        pass
    if state is None:
        _log(f"  ⚠️  '{name}': could not extract state (network / profile issue)")
    return state


async def run_test(post_url: str, profiles: list[str]):
    _log("=" * 60)
    _log("LOVE REACTION TEST")
    _log("=" * 60)
    _log(f"Post:     {post_url}")
    _log(f"Profiles: {', '.join(profiles)}")
    _log("")

    # ── Phase 1: Extract storage states (sequential, same as app) ──
    states: dict[str, dict | None] = {}
    for i, name in enumerate(profiles):
        states[name] = await _extract_state(name)
        if i < len(profiles) - 1:
            await asyncio.sleep(2.5)

    usable = {n: s for n, s in states.items() if s is not None}
    if not usable:
        _log("\n❌ No usable profiles — nothing to test.")
        return

    # ── Phase 2: Shared browser + react (same as app) ──
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        executable_path=CHROME_PATH,
        headless=True,  # Background mode - browser windows hidden
        args=[
            f"--window-size={SMALL_VIEWPORT['width']},{SMALL_VIEWPORT['height']}",
            *MEMORY_FLAGS,
        ],
    )

    try:
        for name, state in usable.items():
            auto = FacebookAutomation(
                log_callback=lambda m, n=name: _log(f"  [{n}] {m}"),
                debug=False,
            )
            await auto.init_from_storage(browser, state, viewport=SMALL_VIEWPORT)
            _log(f"\n── {name} → React (love) ──")
            try:
                ok, msg = await auto._auto_react(post_url, "love")
                icon = "✅" if ok else "❌"
                _log(f"  {icon} {name}: {msg}")
                if ok and "love" in msg.lower() and "already" not in msg.lower():
                    _log(f"  🎉 LOVE APPLIED via picker")
            except Exception as e:
                _log(f"  ❌ {name}: exception: {e}")
            finally:
                await auto.close_context()
    finally:
        await browser.close()
        await pw.stop()

    _log("\n" + "=" * 60)
    _log("TEST COMPLETE")
    _log("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _log("Usage: python test_love_react.py \"<post_url>\" [profile1 profile2 profile3]")
        _log("")
        _log("Examples:")
        _log('  python test_love_react.py "https://www.facebook.com/share/p/1BwFv5EEnv/"')
        _log('  python test_love_react.py "<url>" revikahwinterky yeiriwinterky leilaanelisebc')
        _log("")
        _log("Default profiles: " + ", ".join(DEFAULT_PROFILES))
        sys.exit(1)

    url = sys.argv[1].strip().strip('"')
    names = [n for n in sys.argv[2:]] or DEFAULT_PROFILES
    asyncio.run(run_test(url, names))
