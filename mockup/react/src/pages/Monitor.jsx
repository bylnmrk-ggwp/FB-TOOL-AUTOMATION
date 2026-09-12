import { useEffect, useState } from 'react'
import { PROFILE_MEMORY } from '../data.js'

export default function Monitor({ system, sessions }) {
  const [paused, setPaused] = useState(false)
  const [age, setAge] = useState(3)
  useEffect(() => {
    if (paused) return undefined
    const id = setInterval(() => setAge(a => (a + 1) % 5), 1000)
    return () => clearInterval(id)
  }, [paused])

  const totalMb = PROFILE_MEMORY.reduce((s, p) => s + p.mb, 0)
  const ramPct = Math.round((system.ramUsedGb / system.ramTotalGb) * 100)

  return (
    <div className="monitor">
      <div className="card-head">
        <div>
          <h2 className="card-title">Memory Monitor</h2>
          <div className="muted small mt-xs">RAM per Brave profile, sampled every 5 s.</div>
        </div>
        <div className="btn-row">
          <button type="button" className="btn" onClick={() => setPaused(p => !p)}>{paused ? 'Resume' : 'Pause'}</button>
          <button type="button" className="btn" onClick={() => setAge(0)}>Refresh Now</button>
        </div>
      </div>

      <div className="tiles">
        <div className="card stat">
          <div className="muted">System RAM</div>
          <div className="stat-value">{system.ramUsedGb} / {system.ramTotalGb} GB</div>
          <div className="muted small">{ramPct}% used</div>
        </div>
        <div className="card stat">
          <div className="muted">Browser RAM</div>
          <div className="stat-value">{system.browserGb} GB</div>
          <div className="muted small">total browser RSS</div>
        </div>
        <div className="card stat">
          <div className="muted">Processes</div>
          <div className="stat-value">{system.procs}</div>
          <div className="muted small">browser processes</div>
        </div>
        <div className="card stat">
          <div className="muted">Peak</div>
          <div className="stat-value">{system.peakGb} GB</div>
          <div className="muted small">peak since launch</div>
        </div>
      </div>

      <section className="card grow">
        <div className="card-head">
          <h2 className="card-title">Per-Profile Memory</h2>
          <span className="muted small">{sessions} active session{sessions === 1 ? '' : 's'}</span>
        </div>
        <div className="table-wrap mt-sm">
          <table className="table">
            <thead>
              <tr><th>Profile</th><th className="num">Processes</th><th className="num">RSS</th><th>Share of browser RAM</th></tr>
            </thead>
            <tbody>
              {PROFILE_MEMORY.map(p => {
                const pct = Math.round((p.mb / totalMb) * 100)
                return (
                  <tr key={p.profile}>
                    <td>{p.profile}</td>
                    <td className="num">{p.procs}</td>
                    <td className="num">{p.mb} MB</td>
                    <td><span className="bar" aria-hidden="true"><span style={{ width: pct + '%' }} /></span> <span className="muted small">{pct}%</span></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="muted small">{paused ? 'Paused' : `Updated ${age} s ago`}</div>
    </div>
  )
}
