import { useEffect, useRef, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Header from './components/Header.jsx'
import StatusBar from './components/StatusBar.jsx'
import TabBar from './components/TabBar.jsx'
import Toasts from './components/Toasts.jsx'
import InputPrompt from './components/InputPrompt.jsx'
import Login from './pages/Login.jsx'
import Placeholder from './pages/Placeholder.jsx'
// F2: pages
import Dashboard from './pages/Dashboard.jsx'
import Accounts from './pages/Accounts.jsx'
import Queue from './pages/Queue.jsx'
import Compose from './pages/Compose.jsx'
import Monitor from './pages/Monitor.jsx'
import Log from './pages/Log.jsx'
import { PAGES, useStore, actions } from './store.js'

// Every page receives {page, onNavigate}. Queue/Compose are phase-1 previews
// (real actions disabled); Monitor is live off server.system + counts.
const PAGE_COMPONENTS = {
  dashboard: Dashboard,
  accounts: Accounts,
  queue: Queue,
  compose: Compose,
  monitor: Monitor,
  log: Log,
}

const LS = { theme: 'fbtool.theme', sidebar: 'fbtool.sidebarCollapsed' }
const AUTO_COLLAPSE_BELOW = 1200            // collapse below 1200 px unless the operator pinned a state
const PHONE_QUERY = '(max-width: 767px)'    // below this the sidebar becomes the bottom tab bar
const THEME_OUT_MS = 80, THEME_IN_MS = 140  // theme.py MOTION["theme"] = 220 (80 out, 140 in)
const THEME_COLOR = { light: '#fafafa', dark: '#0f0f11' }   // theme.css --bg per mode, for the browser chrome
const OFFLINE_BANNER_DELAY_MS = 1500        // a reconnect blip shorter than this never shows the banner
const FILL_PAGES = new Set(['accounts', 'monitor', 'log'])
const CHIP_PAGES = new Set(['accounts', 'queue', 'compose'])

// ?theme=dark&sidebar=1 overrides the saved state for that load, so a page
// can be screenshotted headless in a given state.
const params = new URLSearchParams(window.location.search)
const read = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v } catch { return d } }
const write = (k, v) => { try { localStorage.setItem(k, v) } catch { /* private window: nothing to persist to */ } }
const prefersReducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => !!window.matchMedia?.(query).matches)
  useEffect(() => {
    const mq = window.matchMedia?.(query)
    if (!mq) return undefined
    const onChange = () => setMatches(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])
  return matches
}

// True once `flag` has been false for longer than `delay`; a reconnect
// that lands within the delay never flashes the banner.
function useStaleFlag(flag, delay) {
  const [stale, setStale] = useState(false)
  useEffect(() => {
    if (flag) { setStale(false); return undefined }
    const id = setTimeout(() => setStale(true), delay)
    return () => clearTimeout(id)
  }, [flag, delay])
  return stale
}

export default function App() {
  const auth = useStore(s => s.auth)
  const connected = useStore(s => s.connected)
  const server = useStore(s => s.server)
  const counts = useStore(s => s.counts)
  const selected = useStore(s => s.selected)
  const page = useStore(s => s.page)

  const [theme, setTheme] = useState(() => {
    const t = params.get('theme') || read(LS.theme, '')
    if (t === 'dark' || t === 'light') return t
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
  const [pinned, setPinned] = useState(() => {
    const v = params.get('sidebar') ?? read(LS.sidebar, '')
    return v === '1' ? true : v === '0' ? false : null
  })
  const [autoCollapsed, setAutoCollapsed] = useState(() => window.innerWidth < AUTO_COLLAPSE_BELOW)
  const collapsed = pinned ?? autoCollapsed
  const phone = useMediaQuery(PHONE_QUERY)
  const [dipping, setDipping] = useState(false)
  const themeBusy = useRef(false)
  const [navCount, setNavCount] = useState(0)   // 0 until the first navigation: the initial page does not slide
  const offline = useStaleFlag(connected, OFFLINE_BANNER_DELAY_MS)

  useEffect(() => { actions.bootstrap() }, [])
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    write(LS.theme, theme)
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.content = THEME_COLOR[theme]
  }, [theme])
  useEffect(() => {
    const onResize = () => setAutoCollapsed(window.innerWidth < AUTO_COLLAPSE_BELOW)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const navigate = (key) => {
    if (key === page) return
    actions.navigate(key)
    setNavCount(n => n + 1)
  }

  const toggleSidebar = () => {
    const next = !collapsed
    setPinned(next)
    write(LS.sidebar, next ? '1' : '0')
  }

  // Theme toggle: dip to 0.35 over 80 ms, swap the palette at the bottom,
  // come back over 140 ms. Tk dips the whole window; so do we.
  const toggleTheme = () => {
    if (themeBusy.current) return
    const next = theme === 'light' ? 'dark' : 'light'
    if (prefersReducedMotion()) { setTheme(next); return }
    themeBusy.current = true
    setDipping(true)
    setTimeout(() => {
      setTheme(next)
      setDipping(false)
      setTimeout(() => { themeBusy.current = false }, THEME_IN_MS)
    }, THEME_OUT_MS)
  }

  if (auth === 'out') {
    return (
      <>
        <Login theme={theme} onToggleTheme={toggleTheme} />
        <Toasts />
      </>
    )
  }
  if (auth !== 'in') {
    return (
      <>
        <div className="boot" aria-busy="true">
          <div className="spinner" aria-hidden="true" />
          <div className="muted small">Connecting to the PC…</div>
        </div>
        <Toasts />
      </>
    )
  }

  // Derived state.
  const pageMeta = PAGES.find(p => p.key === page) ?? PAGES[0]
  const Page = PAGE_COMPONENTS[pageMeta.key] ?? Placeholder
  const run = server?.run ?? null
  const system = server?.system ?? {}
  const chip = CHIP_PAGES.has(page)
    ? (selected.size ? `${selected.size} selected` : `all logged in (${counts?.active ?? 0})`)
    : ''
  const activity = run
    ? `${run.profile_name ? run.profile_name + ': ' : ''}${run.message || run.kind}`
    : 'Ready'
  const right = [
    `Profiles ${counts?.profiles ?? 0}`,
    `Active ${counts?.active ?? 0}`,
    `RAM ${system.ram_used_gb ?? '?'} / ${system.ram_total_gb ?? '?'} GB`,
    `${system.process_count ?? 0} browser procs`,
  ]
  if (selected.size) right.push(`${selected.size} selected`)
  const banner = offline
    ? 'PC unreachable — reconnecting…'
    : server?.bridge_alive === false
      ? 'The server’s event bridge stopped — restart server.py on the PC'
      : ''

  return (
    <div className={'shell' + (dipping ? ' dipping' : '')}>
      {banner && <div className="banner" role="alert">{banner}</div>}
      <div className="body">
        {!phone && (
          <Sidebar pages={PAGES} active={page} onSelect={navigate} collapsed={collapsed}
                   onToggle={toggleSidebar} theme={theme} />
        )}
        <div className="main">
          <Header title={pageMeta.title} chip={chip} theme={theme} onToggleTheme={toggleTheme}
                  onLogout={() => actions.logout()} />
          {phone && <StatusBar fold activity={activity} run={run} />}
          <div className="content">
            <div key={page} className={'page' + (FILL_PAGES.has(page) ? ' fill' : '') + (navCount ? ' page-enter' : '')}>
              <Page page={pageMeta} onNavigate={navigate} />
            </div>
          </div>
        </div>
      </div>
      {phone
        ? <TabBar pages={PAGES} active={page} onSelect={navigate} />
        : <StatusBar activity={activity} run={run} right={right.join('  ·  ')} />}
      {server?.pending_input && <InputPrompt prompt={server.pending_input} />}
      <Toasts />
    </div>
  )
}
