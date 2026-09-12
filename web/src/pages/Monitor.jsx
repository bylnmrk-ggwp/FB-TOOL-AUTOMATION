import { useStore, actions } from '../store.js'

// Live memory monitor. Every value comes from the store: server.system is the
// dict manager.get_memory_stats() feeds the bridge (ram_used_gb, ram_total_gb,
// browser_mb, process_count, peak_browser_mb) and counts.active is the number
// of logged-in Brave profiles. Phase 1 has no per-profile memory breakdown in
// the state, so the mockup's PROFILE_MEMORY table is a muted note instead.
const EM = '—'
const gb = (mb) => (typeof mb === 'number' && isFinite(mb)) ? `${(mb / 1024).toFixed(1)} GB` : EM
const num = (v) => (v === null || v === undefined) ? EM : v

export default function Monitor() {
  const server = useStore(s => s.server)
  const counts = useStore(s => s.counts)
  const system = server?.system ?? {}

  const ramUsed = system.ram_used_gb
  const ramTotal = system.ram_total_gb
  const ramText = (ramUsed === null || ramUsed === undefined || ramTotal === null || ramTotal === undefined)
    ? EM
    : `${ramUsed} / ${ramTotal} GB`
  const ramPct = (typeof ramUsed === 'number' && typeof ramTotal === 'number' && ramTotal > 0)
    ? `${Math.round((ramUsed / ramTotal) * 100)}% used`
    : 'system memory'
  const active = counts?.active

  return (
    <div className="monitor">
      <div className="card-head">
        <div>
          <h2 className="card-title">Memory Monitor</h2>
          <div className="muted small mt-xs">
            Live from the PC {'—'} {active === null || active === undefined ? EM : active} active session{active === 1 ? '' : 's'}.
          </div>
        </div>
        <div className="btn-row">
          <button type="button" className="btn" onClick={() => actions.refreshState()}>Refresh Now</button>
        </div>
      </div>

      <div className="tiles">
        <div className="card stat">
          <div className="muted">System RAM</div>
          <div className="stat-value">{ramText}</div>
          <div className="muted small">{ramPct}</div>
        </div>
        <div className="card stat">
          <div className="muted">Browser RAM</div>
          <div className="stat-value">{gb(system.browser_mb)}</div>
          <div className="muted small">total browser RSS</div>
        </div>
        <div className="card stat">
          <div className="muted">Processes</div>
          <div className="stat-value">{num(system.process_count)}</div>
          <div className="muted small">browser processes</div>
        </div>
        <div className="card stat">
          <div className="muted">Peak</div>
          <div className="stat-value">{gb(system.peak_browser_mb)}</div>
          <div className="muted small">peak since launch</div>
        </div>
      </div>

      <section className="card grow">
        <div className="card-head">
          <h2 className="card-title">Per-Profile Memory</h2>
          <span className="muted small">{active === null || active === undefined ? EM : active} active session{active === 1 ? '' : 's'}</span>
        </div>
        <p className="muted mt-sm">
          Per-profile breakdown runs in the desktop app (python main.py --tk).
        </p>
      </section>
    </div>
  )
}
