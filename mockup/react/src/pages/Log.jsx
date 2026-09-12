import { useEffect, useRef } from 'react'

export default function Log({ lines, onClear }) {
  const view = useRef(null)
  useEffect(() => {
    const el = view.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines.length])

  return (
    <div className="log">
      <div className="card-head">
        <h2 className="card-title">Log Output</h2>
        <button type="button" className="btn sm" onClick={onClear} disabled={lines.length === 0}>Clear Log</button>
      </div>
      <div className="log-view" ref={view} role="log" aria-live="polite">
        {lines.length === 0
          ? <div className="muted">Log is empty. Runs, sheet syncs and errors appear here.</div>
          : lines.map((l, i) => (
            <div key={i} className={'log-line ' + l.kind}><span className="t">[{l.time}]</span> {l.text}</div>
          ))}
      </div>
    </div>
  )
}
