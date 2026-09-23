import { useEffect, useState } from 'react'
import StatCard from '../components/StatCard.jsx'
import Charts from '../components/Charts.jsx'
import { useStore, actions } from '../store.js'

const REFRESH_MS = 5000     // counts refetch while the page is on screen
const MAX_ALERTS = 8

// Age of the last successful sheet sync, ticking once a second.
// `sheet_last_ok` is the PC's time.time(); 0 means the watcher has not
// completed a poll yet. Clock skew between phone and PC is clamped at 0.
function useSheetAge(lastOk) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  if (!lastOk) return null
  return Math.max(0, Math.round(now / 1000 - lastOk))
}

export default function Dashboard({ onNavigate }) {
  const counts = useStore(s => s.counts)
  const server = useStore(s => s.server)
  const log = useStore(s => s.log)

  useEffect(() => {
    const id = setInterval(actions.refreshState, REFRESH_MS)
    return () => clearInterval(id)
  }, [])

  const run = server?.run ?? null
  const system = server?.system ?? {}
  const pending = counts?.pending ?? 0
  const unlinked = counts?.pending_unlinked ?? 0
  const n = Math.max(0, pending - unlinked)
  const loginActive = !!server?.login_run_active
  const sheetAge = useSheetAge(server?.sheet_last_ok ?? 0)
  const pct = run && run.total ? Math.min(100, Math.round((run.current / run.total) * 100)) : 0

  const alerts = []
  for (let i = log.length - 1; i >= 0 && alerts.length < MAX_ALERTS; i--) {
    if (log[i].level === 'error') alerts.push(log[i])
  }

  const openLog = () => (onNavigate ? onNavigate('log') : actions.navigate('log'))

  const loginPending = () => {
    if (n === 0 || loginActive) return
    const ok = window.confirm(
      `Log in ${n} pending account${n === 1 ? '' : 's'}?\n\nThis opens Brave on the PC for each one, in turn.`)
    if (ok) actions.loginPending()
  }

  return (
    <div className="dash">
      <div className="stats">
        <StatCard title="Total accounts" value={counts?.total} hint="roster rows" />
        <StatCard title="Logged in" value={counts?.logged_in} hint="live profile check" />
        <StatCard title="Need login" value={counts?.pending} hint="blank STATUS on the sheet" />
        <StatCard title="Disabled" value={counts?.disabled} hint="by Facebook" />
      </div>

      <div className="dash-action">
        <button type="button" className="btn accent" disabled={n === 0 || loginActive} onClick={loginPending}>
          {loginActive ? 'Logging in…' : `Log in ${n} pending account${n === 1 ? '' : 's'}`}
        </button>
        {unlinked > 0 && (
          <span className="muted small">
            {unlinked} pending row{unlinked === 1 ? ' has' : 's have'} no Brave profile {'—'} link them on the Accounts page
          </span>
        )}
      </div>

      <Charts />

      <div className="row2">
        <section className="card">
          <h2 className="card-title">Run activity</h2>
          <div className="muted mt-sm">
            {run ? `${run.profile_name ? run.profile_name + ': ' : ''}${run.message || run.kind}` : 'Idle'}
          </div>
          <div className="progress mt-xs" aria-hidden={!run}><span style={{ width: pct + '%' }} /></div>
          <div className="muted small mt-xs">{run ? `${run.current}/${run.total}` : ' '}</div>
          <div className="kv mt-sm">
            <span className="muted">Last run</span>
            <span>{server?.last_run_summary || 'No run yet'}</span>
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">System</h2>
          <div className="kv-list">
            <div className="kv">
              <span className="muted">RAM</span>
              <span>{system.ram_used_gb ?? '?'} / {system.ram_total_gb ?? '?'} GB</span>
            </div>
            <div className="kv"><span className="muted">Browser processes</span><span>{system.process_count ?? 0}</span></div>
            <div className="kv"><span className="muted">Active sessions</span><span>{counts?.active ?? 0}</span></div>
            <div className="kv">
              <span className="muted">Sheet sync</span>
              <span>{sheetAge === null ? 'not started' : `${sheetAge} s ago`}</span>
            </div>
          </div>
        </section>

        <section className="card alerts" role="link" tabIndex={0} onClick={openLog}
                 onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openLog() } }}>
          <div className="card-head">
            <h2 className="card-title">Recent alerts</h2>
            <button type="button" className="btn sm" onClick={e => { e.stopPropagation(); openLog() }}>Open log</button>
          </div>
          {alerts.length === 0
            ? <div className="muted small mt-sm">No errors in this session.</div>
            : (
              <ul className="alert-list">
                {alerts.map((a, i) => (
                  <li key={`${a.stamp}-${i}`}><span className="t">{a.stamp}</span>  {a.text}</li>
                ))}
              </ul>
            )}
        </section>
      </div>
    </div>
  )
}
