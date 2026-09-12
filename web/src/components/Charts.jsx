import { useStore } from '../store.js'

// Account-status visualised as an SVG donut plus a horizontal bar breakdown.
// No chart library: hand-rolled SVG that reuses the app's semantic colour
// tokens, so both charts track the light/dark theme like the rest of the UI.

const R = 54                       // donut radius
const C = 2 * Math.PI * R          // circumference (dash length basis)

// Split the roster counts into four disjoint, non-negative buckets that
// always sum to `total`. `other` absorbs any rows that are none of the three
// (and guards against the parts overshooting total from a mid-sync read).
function buckets(counts) {
  const total = Math.max(0, counts?.total ?? 0)
  const logged = Math.max(0, counts?.logged_in ?? 0)
  const pending = Math.max(0, counts?.pending ?? 0)
  const disabled = Math.max(0, counts?.disabled ?? 0)
  const other = Math.max(0, total - logged - pending - disabled)
  return {
    total,
    parts: [
      { key: 'logged', label: 'Logged in', value: logged, color: 'var(--success)' },
      { key: 'pending', label: 'Need login', value: pending, color: 'var(--accent)' },
      { key: 'disabled', label: 'Disabled', value: disabled, color: 'var(--error)' },
      { key: 'other', label: 'Other', value: other, color: 'var(--dot-unknown)' },
    ],
  }
}

export default function Charts() {
  const counts = useStore(s => s.counts)
  const { total, parts } = buckets(counts)
  const max = Math.max(1, ...parts.map(p => p.value))

  // Lay the visible slices end to end around the ring. strokeDashoffset is
  // negative so each slice starts where the previous one ended.
  let acc = 0
  const ring = parts
    .filter(p => p.value > 0)
    .map(p => {
      const frac = total > 0 ? p.value / total : 0
      const slice = {
        ...p,
        dash: frac * C,
        offset: -acc * C,
        pct: Math.round(frac * 100),
      }
      acc += frac
      return slice
    })

  const summary = ring.length
    ? ring.map(s => `${s.value} ${s.label}`).join(', ') + ` of ${total} total`
    : 'no accounts yet'

  return (
    <div className="charts">
      <section className="card chart-card">
        <h2 className="card-title">Account status</h2>
        <div className="donut-wrap">
          <svg className="donut" viewBox="0 0 140 140" role="img"
               aria-label={`Account status: ${summary}`}>
            <circle cx="70" cy="70" r={R} fill="none" stroke="var(--track)" strokeWidth="20" />
            {total > 0 && ring.map(s => (
              <circle key={s.key} cx="70" cy="70" r={R} fill="none"
                      stroke={s.color} strokeWidth="20"
                      strokeDasharray={`${s.dash} ${C - s.dash}`}
                      strokeDashoffset={s.offset}
                      transform="rotate(-90 70 70)">
                <title>{s.label}: {s.value} ({s.pct}%)</title>
              </circle>
            ))}
            <text x="70" y="66" className="donut-num" textAnchor="middle">{total}</text>
            <text x="70" y="86" className="donut-lbl" textAnchor="middle">accounts</text>
          </svg>
          <ul className="legend">
            {parts.map(p => (
              <li key={p.key}>
                <span className="swatch" style={{ background: p.color }} aria-hidden="true" />
                <span className="muted">{p.label}</span>
                <span className="legend-val">{p.value}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="card chart-card">
        <h2 className="card-title">Breakdown</h2>
        <div className="bars">
          {parts.map(p => (
            <div className="bar-row" key={p.key}>
              <span className="bar-label muted">{p.label}</span>
              <span className="bar-track">
                <span className="bar-fill"
                      style={{ width: (p.value / max * 100) + '%', background: p.color }} />
              </span>
              <span className="bar-val">{p.value}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
