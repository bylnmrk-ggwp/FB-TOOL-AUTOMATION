import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store.js'

// Live tail of the store's log (the same lines LogRing writes on the PC).
// Pause stops the auto-scroll so a line can be read while the run keeps
// talking; Clear hides what is on screen for this device only, the PC's
// ring and file keep everything.
export default function Log() {
  const log = useStore(s => s.log)
  const [paused, setPaused] = useState(false)
  const [filter, setFilter] = useState('')
  // The last line on screen when Clear was pressed. Lines are stable
  // objects across reduce, so the cut survives the ring's trimming; once
  // the line has left the ring (or a re-login replaced the log) it is
  // simply gone and everything shows again.
  const [clearedAt, setClearedAt] = useState(null)
  const view = useRef(null)

  const start = clearedAt ? log.lastIndexOf(clearedAt) + 1 : 0
  const needle = filter.trim().toLowerCase()
  const lines = []
  for (let i = start; i < log.length; i++) {
    const l = log[i]
    if (!needle || l.text.toLowerCase().includes(needle)) lines.push(l)
  }

  useEffect(() => {
    const el = view.current
    if (el && !paused) el.scrollTop = el.scrollHeight
  }, [lines.length, paused, needle])

  const clear = () => setClearedAt(log.length ? log[log.length - 1] : null)

  return (
    <div className="log">
      <div className="toolbar">
        <h2 className="card-title">Log Output</h2>
        <span className="spacer" />
        <input className="input search" value={filter} placeholder="filter lines" aria-label="Filter log lines"
               onChange={e => setFilter(e.target.value)} />
        <button type="button" className={'btn sm' + (paused ? ' toggled' : '')} aria-pressed={paused}
                onClick={() => setPaused(p => !p)}>
          {paused ? 'Resume' : 'Pause'}
        </button>
        <button type="button" className="btn sm" onClick={clear} disabled={log.length === 0 || start >= log.length}>Clear</button>
      </div>
      <div className="log-view" ref={view} role="log" aria-live={paused ? 'off' : 'polite'}>
        {lines.length === 0
          ? <div className="muted">{needle ? 'No lines match the filter.' : 'Log is empty. Runs, sheet syncs and errors appear here.'}</div>
          : lines.map((l, i) => (
            <div key={start + i} className={'log-line ' + (l.level || 'info')}><span className="t">[{l.stamp}]</span> {l.text}</div>
          ))}
      </div>
      <div className="foot">
        <span className="muted">
          {paused ? 'Paused — new lines still arrive, the view stays put' : 'Following new lines'}
          {needle ? ` · ${lines.length} of ${log.length - start} shown` : ''}
        </span>
      </div>
    </div>
  )
}
