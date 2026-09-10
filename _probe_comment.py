import asyncio, json, sys
from pathlib import Path

from playwright.async_api import async_playwright
from src.core.facebook_automation import CHROME_PATH, SMALL_VIEWPORT, MEMORY_FLAGS
from src.storage import state_cache

PID = "pfbid025XFwngkQ7fTEKPkRgzDAMTCcgRDVr3WGBippBwrwhHbuSyPJD1StEgmEkEaGQhKl"
PROFILE = sys.argv[1] if len(sys.argv) > 1 else "shaunelteiri"


async def main():
    state = state_cache.load_state(PROFILE)
    print(f"[probe] profile={PROFILE}")
    if not state:
        return
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        executable_path=CHROME_PATH, headless=False,
        args=[f"--window-size={SMALL_VIEWPORT['width']},{SMALL_VIEWPORT['height']}", "--headless=new", *MEMORY_FLAGS])
    context = await browser.new_context(storage_state=state, viewport=SMALL_VIEWPORT)
    page = await context.new_page()
    page.set_default_timeout(15000)

    await page.goto(f"https://www.facebook.com/kalbolitorunner/posts/{PID}", timeout=30000, wait_until="domcontentloaded")
    await asyncio.sleep(8)

    # Identify the real scroll container
    sc = await page.evaluate("""() => {
        const els = [document.scrollingElement, document.body, ...[...document.querySelectorAll('*')]];
        const out = [];
        for (const el of els) {
            const st = getComputedStyle(el);
            const canScroll = (st.overflowY === 'auto' || st.overflowY === 'scroll') &&
                              el.scrollHeight > el.clientHeight + 100;
            if (canScroll) out.push({tag: el.tagName, sh: el.scrollHeight, ch: el.clientHeight,
                                     st: st.overflowY, id: el.id, cls: (el.className||'').slice(0,40)});
            if (out.length >= 5) break;
        }
        return out;
    }""")
    print("[probe] scroll containers:", json.dumps(sc, ensure_ascii=False)[:1200])

    # Scroll the right container to load posts; hunt for the target
    hit = None
    for i in range(12):
        res = await page.evaluate(f"""() => {{
            const pid = {json.dumps(PID)};
            let scrolled = null;
            const els = [document.scrollingElement, document.body, ...[...document.querySelectorAll('*')]]
                .filter(el => {{
                    const st = getComputedStyle(el);
                    return (st.overflowY === 'auto' || st.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 100;
                }});
            if (els.length) {{
                const el = els[0];
                el.scrollTop += 1200;
                scrolled = el.tagName;
            }}
            const art = [...document.querySelectorAll('[role="article"]')].find(a =>
                [...a.querySelectorAll('a')].some(x => x.href.includes(pid)));
            return {{
                scrolled,
                n_articles: document.querySelectorAll('[role="article"]').length,
                hit_y: art ? Math.round(art.getBoundingClientRect().y) : null,
                body_len: document.body.innerText.length,
            }};
        }}""")
        if res["hit_y"] is not None:
            hit = res
            print(f"[probe] step {i}: FOUND target article at y={res['hit_y']} (scrolled via {res['scrolled']})")
            break
        if i % 3 == 0:
            print(f"[probe] step {i}: articles={res['n_articles']} body_len={res['body_len']} scroller={res['scrolled']}")
        await asyncio.sleep(1.5)

    if not hit:
        print("[probe] target not found after scroll")
        await page.screenshot(path=str(Path.home() / ".autoshare" / "debug" / "probe_scroll_nohit.png"))
    else:
        # Now click the comment button on the target article (scroll it into view first)
        res = await page.evaluate(f"""() => {{
            const pid = {json.dumps(PID)};
            const art = [...document.querySelectorAll('[role="article"]')].find(a =>
                [...a.querySelectorAll('a')].some(x => x.href.includes(pid)));
            art.scrollIntoView({{block:'center'}});
            const btn = [...art.querySelectorAll('[role="button"]')].find(b => {{
                const r = b.getBoundingClientRect();
                return r.width>0 && r.height>0 && (b.getAttribute('aria-label')||'').toLowerCase().includes('comment');
            }});
            if (!btn) return 'no comment btn in target article';
            btn.scrollIntoView({{block:'center'}});
            btn.click();
            return 'clicked: ' + btn.getAttribute('aria-label');
        }}""")
        print("[probe] click:", res)
        await asyncio.sleep(4)
        after = await page.evaluate("""() => {
            const q = sel => [...document.querySelectorAll(sel)].filter(e => {
                const r = e.getBoundingClientRect(); return r.width>0 && r.height>0;
            }).map(e => {
                const r = e.getBoundingClientRect();
                return {aria: e.getAttribute('aria-label'), ph: e.getAttribute('aria-placeholder'),
                        y:Math.round(r.y), x:Math.round(r.x), w:Math.round(r.width), h:Math.round(r.height)};
            }).slice(0,10);
            return { editable: q('[contenteditable="true"], textarea, div[role="textbox"]'),
                     dialogs: document.querySelectorAll('[role="dialog"]').length };
        }""")
        print("[probe] after click:", json.dumps(after, ensure_ascii=False)[:1500])
        await page.screenshot(path=str(Path.home() / ".autoshare" / "debug" / "probe_scroll_hit.png"))

    await browser.close()
    await pw.stop()


asyncio.run(main())
