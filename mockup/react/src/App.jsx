import { useCallback, useEffect, useRef, useState } from 'react'
import Sidebar from './components/Sidebar.jsx'
import Header from './components/Header.jsx'
import StatusBar from './components/StatusBar.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Accounts from './pages/Accounts.jsx'
import Queue from './pages/Queue.jsx'
import Compose from './pages/Compose.jsx'
import Monitor from './pages/Monitor.jsx'
import Log from './pages/Log.jsx'
import { ACCOUNTS, QUEUE_ITEMS, LOG_LINES, SYSTEM, counts } from './data.js'

// Same registry as MainWindow.PAGES: key, title, Segoe Fluent glyph, Unicode fallback.
export const PAGES = [
  { key: 'dashboard', title: 'Dashboard', glyph: '', fallback: '▣' },
  { key: 'accounts',  title: 'Accounts',  glyph: '', fallback: '◉' },
  { key: 'queue',     title: 'Queue',     glyph: '', fallback: '≡' },
  { key: 'compose',   title: 'Compose',   glyph: '', fallback: '✎' },
  { key: 'monitor',   title: 'Monitor',   glyph: '', fallback: '◔' },
  { key: 'log',       title: 'Log',       glyph: '', fallback: '▤' },
]

const LS = { theme: 'fbtool.theme', sidebar: 'fbtool.sidebarCollapsed', page: 'fbtool.page' }
const AUTO_COLLAPSE_BELOW = 1200            // spec: collapse below px(1200) unless the operator pinned a state
const THEME_OUT_MS = 80, THEME_IN_MS = 140  // theme.py MOTION["theme"] = 220 (80 out, 140 in)
const FILL_PAGES = new Set(['accounts', 'monitor', 'log'])
const CHIP_PAGES = new Set(['accounts', 'queue', 'compose'])
const IDLE_RUN = { active: false, kind: '', done: 0, total: 0, profile: '', message: '' }

// ?page=accounts&theme=dark&sidebar=1 overrides the saved state for that load,
// so a page can be linked to directly (and screenshotted headless).
const params = new URLSearchParams(window.location.search)
const read = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v } catch { return d } }
const write = (k, v) => { try { localStorage.setItem(k, v) } catch { /* private window: nothing to persist to */ } }
const prefersReducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const stamp = () => new Date().toTimeString().slice(0, 8)
const hhmm = () => new Date().toTimeString().slice(0, 5)
const short = (profile) => profile.replace(/^Profile \d+ - /, '')

export default function App() {
  const [page, setPage] = useState(() => {
    const p = params.get('page') || read(LS.page, 'dashboard')
    return PAGES.some(x => x.key === p) ? p : 'dashboard'
  })
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
  const [dipping, setDipping] = useState(false)
  const themeBusy = useRef(false)
  const [navCount, setNavCount] = useState(0)   // 0 until the first navigation: the initial page does not slide

  const [accounts, setAccounts] = useState(ACCOUNTS)
  const [selected, setSelected] = useState(() => new Set())
  const [queue, setQueue] = useState(QUEUE_ITEMS)
  const [log, setLog] = useState(LOG_LINES)
  const [run, setRun] = useState(IDLE_RUN)
  const [lastSummary, setLastSummary] = useState('132 ok · 8 failed · 20:11')
  const timer = useRef(null)

  useEffect(() => { document.documentElement.dataset.theme = theme; write(LS.theme, theme) }, [theme])
  useEffect(() => { write(LS.page, page) }, [page])
  useEffect(() => {
    const onResize = () => setAutoCollapsed(window.innerWidth < AUTO_COLLAPSE_BELOW)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  useEffect(() => () => clearInterval(timer.current), [])

  const appendLog = useCallback((kind, text) => setLog(l => [...l, { time: stamp(), kind, text }]), [])
  const clearLog = () => setLog([])

  const navigate = (key) => {
    if (key === page) return
    setPage(key)
    setNavCount(n => n + 1)
  }

  const toggleSidebar = () => {
    const next = !collapsed
    setPinned(next)
    write(LS.sidebar, next ? '1' : '0')
  }

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

  // Fake runs. One step every second or so, so the progress bar, the
  // count-up and the status bar have something to show. No browser here.

  const loginAccounts = (usernames) => {
    if (run.active || usernames.length === 0) return
    const total = usernames.length
    let i = 0, failed = 0
    const markInProgress = (u) => setAccounts(as => as.map(a => a.username === u ? { ...a, sheetStatus: 'LOGGING IN' } : a))
    appendLog('info', `Logging in ${total} account${total === 1 ? '' : 's'}, one at a time, headless`)
    setRun({ active: true, kind: 'login', done: 0, total, profile: usernames[0], message: 'logging in' })
    markInProgress(usernames[0])
    timer.current = setInterval(() => {
      const u = usernames[i]
      const checkpoint = total > 1 && i === 1      // one checkpoint per run, for realism
      if (checkpoint) failed += 1
      setAccounts(as => as.map(a => a.username !== u ? a : checkpoint
        ? { ...a, sheetStatus: 'NOT LOGGED IN / CHECKPOINT', loggedIn: false, reason: `checkpoint — finish with scripts/login_accounts.py --only ${u}` }
        : { ...a, sheetStatus: 'LOGGED IN', loggedIn: true, reason: '' }))
      appendLog(checkpoint ? 'error' : 'ok', checkpoint ? `✗ ${u}: checkpoint, cannot be solved headless` : `✓ ${u}: logged in, sheet updated`)
      i += 1
      if (i < total) {
        markInProgress(usernames[i])
        setRun({ active: true, kind: 'login', done: i, total, profile: usernames[i], message: 'logging in' })
      } else {
        clearInterval(timer.current)
        const summary = `${total - failed} ok · ${failed} failed · ${hhmm()}`
        setLastSummary(summary)
        setRun(IDLE_RUN)
        appendLog('info', `Pending login finished: ${summary}`)
      }
    }, 1400)
  }

  const startQueue = () => {
    const items = queue.filter(q => q.status === 'pending' || q.status === 'failed')
    if (run.active || items.length === 0) return
    const total = items.length
    let i = 0
    const setStatus = (id, status) => setQueue(qs => qs.map(q => q.id === id ? { ...q, status } : q))
    const begin = (n) => {
      setStatus(items[n].id, 'running')
      setRun({ active: true, kind: 'queue', done: n, total, profile: short(items[n].profile), message: items[n].action.toLowerCase() })
    }
    appendLog('info', `Queue started: ${total} item${total === 1 ? '' : 's'}`)
    begin(0)
    timer.current = setInterval(() => {
      const it = items[i]
      setStatus(it.id, 'done')
      appendLog('ok', `✓ ${short(it.profile)}: ${it.action.toLowerCase()} done`)
      i += 1
      if (i < total) {
        begin(i)
      } else {
        clearInterval(timer.current)
        const summary = `${total} ok · 0 failed · ${hhmm()}`
        setLastSummary(summary)
        setRun(IDLE_RUN)
        appendLog('info', `Queue finished: ${summary}`)
      }
    }, 1200)
  }

  // Derived state.

  const c = counts(accounts)
  const title = PAGES.find(p => p.key === page).title
  const chip = CHIP_PAGES.has(page)
    ? (selected.size ? `${selected.size} selected` : `all logged in (${c.loggedIn})`)
    : ''
  // The scope Queue and Compose act on: checked rows with a profile, else every logged-in profile.
  const scope = selected.size
    ? accounts.filter(a => selected.has(a.username) && a.profile)
    : accounts.filter(a => a.loggedIn && a.sheetStatus !== 'DISABLED')
  const alerts = log.filter(l => l.kind === 'error').slice(-8).reverse()

  let body
  if (page === 'dashboard') {
    body = <Dashboard counts={c} run={run} lastSummary={lastSummary} alerts={alerts} system={SYSTEM}
                      onLoginPending={() => loginAccounts(c.pendingUsernames)} onOpenLog={() => navigate('log')} />
  } else if (page === 'accounts') {
    body = <Accounts accounts={accounts} selected={selected} setSelected={setSelected} run={run}
                     onLoginSelected={loginAccounts} log={appendLog} />
  } else if (page === 'queue') {
    body = <Queue queue={queue} setQueue={setQueue} scope={scope} run={run} onStart={startQueue} log={appendLog} />
  } else if (page === 'compose') {
    body = <Compose scope={scope} run={run} log={appendLog} />
  } else if (page === 'monitor') {
    body = <Monitor system={SYSTEM} sessions={c.loggedIn} />
  } else {
    body = <Log lines={log} onClear={clearLog} />
  }

  const activity = run.active ? `${run.profile}: ${run.message}` : 'Ready'
  const right = [`Profiles ${c.total}`, `Logged in ${c.loggedIn}`, `RAM ${SYSTEM.ramUsedGb} / ${SYSTEM.ramTotalGb} GB`, `${SYSTEM.procs} browser procs`]
  if (selected.size) right.push(`${selected.size} selected`)

  return (
    <div className={'shell' + (dipping ? ' dipping' : '')}>
      <div className="body">
        <Sidebar pages={PAGES} active={page} onSelect={navigate} collapsed={collapsed} onToggle={toggleSidebar} theme={theme} />
        <div className="main">
          <Header title={title} chip={chip} theme={theme} onToggleTheme={toggleTheme}
                  onLogout={() => appendLog('info', 'Log Out pressed (mockup: nothing to log out of)')} />
          <div className="content">
            <div key={page} className={'page' + (FILL_PAGES.has(page) ? ' fill' : '') + (navCount ? ' page-enter' : '')}>
              {body}
            </div>
          </div>
        </div>
      </div>
      <StatusBar activity={activity} run={run} right={right.join('  ·  ')} />
    </div>
  )
}
