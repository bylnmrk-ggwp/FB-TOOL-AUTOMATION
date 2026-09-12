import { useEffect, useRef, useState } from 'react'

const COUNT_MS = 300   // theme.py MOTION["count"]
const easeOutCubic = t => 1 - Math.pow(1 - t, 3)
const reduced = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Count-up from the previous value to the new one, like effects.count_up.
function useCountUp(value) {
  const [shown, setShown] = useState(0)
  const cur = useRef(0)
  useEffect(() => {
    const a = cur.current, b = value
    if (a === b) return undefined
    if (reduced()) { cur.current = b; setShown(b); return undefined }
    const start = performance.now()
    let raf = 0
    const step = (now) => {
      const t = Math.min(1, (now - start) / COUNT_MS)
      cur.current = Math.round(a + (b - a) * easeOutCubic(t))
      setShown(cur.current)
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return shown
}

function Stat({ title, value, hint }) {
  const n = useCountUp(value)
  return (
    <div className="card stat">
      <div className="muted">{title}</div>
      <div className="stat-value">{n}</div>
      <div className="muted small">{hint}</div>
    </div>
  )
}

// The sheet watcher polls every 20 s; the age counts up and resets.
function useSyncAge() {
  const [age, setAge] = useState(12)
  useEffect(() => {
    const id = setInterval(() => setAge(a => (a + 1) % 20), 1000)
    return () => clearInterval(id)
  }, [])
  return age
}

export default function Dashboard({ counts, run, lastSummary, alerts, system, onLoginPending, onOpenLog }) {
  const n = counts.pendingUsernames.length
  const loginRunning = run.active && run.kind === 'login'
  const syncAge = useSyncAge()
  const pct = run.total ? (run.done / run.total) * 100 : 0
  const unlinked = counts.pendingUnlinked

  return (
    <div className="dash">
      <div className="stats">
        <Stat title="Total accounts" value={counts.total} hint="roster rows" />
        <Stat title="Logged in" value={counts.loggedIn} hint="status ok" />
        <Stat title="Need login" value={counts.pending} hint="blank STATUS on the sheet" />
        <Stat title="Disabled" value={counts.disabled} hint="by Facebook" />
      </div>

      <div className="dash-action">
        <button type="button" className="btn accent" disabled={n === 0 || run.active} onClick={onLoginPending}>
          {loginRunning ? 'Logging in…' : `Log in ${n} pending account${n === 1 ? '' : 's'}`}
        </button>
        {unlinked > 0 && (
          <span className="muted small">
            {unlinked} pending row{unlinked === 1 ? ' has' : 's have'} no Brave profile {'—'} run scripts/provision_profiles.py
          </span>
        )}
      </div>

      <div className="row2">
        <section className="card">
          <h2 className="card-title">Run activity</h2>
          <div className="muted mt-sm">{run.active ? `${run.profile}: ${run.message}` : 'Idle'}</div>
          <div className="progress mt-xs"><span style={{ width: pct + '%' }} /></div>
          <div className="muted small mt-xs">{run.active ? `${run.done}/${run.total}` : ' '}</div>
          <div className="kv mt-sm"><span className="muted">Last run</span><span>{lastSummary || 'No run yet'}</span></div>
        </section>

        <section className="card">
          <h2 className="card-title">System</h2>
          <div className="kv-list">
            <div className="kv"><span className="muted">RAM</span><span>{system.ramUsedGb} / {system.ramTotalGb} GB</span></div>
            <div className="kv"><span className="muted">Browser processes</span><span>{system.procs}</span></div>
            <div className="kv"><span className="muted">Active sessions</span><span>{counts.loggedIn}</span></div>
            <div className="kv"><span className="muted">Sheet sync</span><span>{syncAge} s ago</span></div>
          </div>
        </section>

        <section className="card alerts" role="link" tabIndex={0} onClick={onOpenLog}
                 onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenLog() } }}>
          <div className="card-head">
            <h2 className="card-title">Recent alerts</h2>
            <button type="button" className="btn sm" onClick={e => { e.stopPropagation(); onOpenLog() }}>Open log</button>
          </div>
          {alerts.length === 0
            ? <div className="muted small mt-sm">No errors in this session.</div>
            : <ul className="alert-list">{alerts.map((a, i) => <li key={i}><span className="t">{a.time}</span>  {a.text}</li>)}</ul>}
        </section>
      </div>
    </div>
  )
}
