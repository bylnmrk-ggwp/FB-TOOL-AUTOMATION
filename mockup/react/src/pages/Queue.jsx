import { useState } from 'react'
import { PRESETS } from '../data.js'

const REACTIONS = ['Like', 'Love', 'Care', 'Haha', 'Wow']
const STATUS = {
  pending: { kind: 'off', text: '○ Pending' },
  running: { kind: 'running', text: '◌ Running…' },
  done: { kind: 'ok', text: '● Done' },
  failed: { kind: 'disabled', text: '✕ Failed' },
}
const short = (p) => p.replace(/^Profile \d+ - /, '')
let nextId = 1000

export default function Queue({ queue, setQueue, scope, run, onStart, log }) {
  const [url, setUrl] = useState('')
  const [comment, setComment] = useState('')
  const [reaction, setReaction] = useState('Like')
  const [reactOnly, setReactOnly] = useState(false)
  const [watchUrl, setWatchUrl] = useState('')
  const [minutes, setMinutes] = useState(10)
  const [watching, setWatching] = useState(false)
  const [mode, setMode] = useState('headless')
  const [picked, setPicked] = useState(null)
  const busy = run.active
  const runnable = queue.filter(q => q.status === 'pending' || q.status === 'failed').length
  const n = scope.length

  const add = () => {
    const u = url.trim()
    if (!u) { log('error', '✗ Add to Queue: Post URL is empty'); return }
    if (n === 0) { log('error', '✗ Add to Queue: no profile in scope'); return }
    const action = reactOnly ? `React (${reaction})` : 'Share to timeline'
    const items = scope.map(a => ({ id: nextId++, profile: a.profile, action, url: u, comment: comment.trim(), status: 'pending' }))
    setQueue(q => [...q, ...items])
    setUrl('')
    setComment('')
    log('info', `Added ${items.length} item${items.length === 1 ? '' : 's'} to the queue (${action})`)
  }
  const loadPresets = () => {
    const items = PRESETS.flatMap(name => scope.slice(0, 2).map(a => ({
      id: nextId++, profile: a.profile, action: 'Share to timeline', url: `preset: ${name}`, comment: '', status: 'pending',
    })))
    setQueue(q => [...q, ...items])
    log('info', `Loaded ${PRESETS.length} presets: ${items.length} item${items.length === 1 ? '' : 's'} added`)
  }
  const remove = () => {
    if (picked === null) return
    setQueue(q => q.filter(x => x.id !== picked))
    setPicked(null)
  }
  const clearAll = () => { setQueue([]); setPicked(null) }

  return (
    <div className="queue">
      <div>
        <h2 className="card-title">Share Queue</h2>
        <p className="muted small mt-xs">Load saved presets or add timeline shares {'—'} each item uses its own profile.</p>
      </div>

      <div>
        <div className="muted small">Acting on {n} profile{n === 1 ? '' : 's'}</div>
        <div className="profile-strip mt-xs">
          {scope.map(a => (
            <span key={a.username} className="pill">
              <span className={'d' + (a.loggedIn ? '' : ' off')} aria-hidden="true">{'●'}</span>{short(a.profile)}
            </span>
          ))}
          {n === 0 && <span className="muted small">No profile in scope. Check rows on the Accounts page.</span>}
        </div>
      </div>

      <section className="card">
        <h2 className="card-title">Quick Add</h2>
        <p className="muted small mt-xs">Choose a command, fill in the form, then add it to the queue.</p>
        <div className="form-grid mt-md">
          <label className="field wide"><span>Post URL</span>
            <input className="input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.facebook.com/..." /></label>
          <label className="field"><span>Comment</span>
            <input className="input" value={comment} onChange={e => setComment(e.target.value)} placeholder="optional" /></label>
          <label className="field"><span>Reaction</span>
            <select className="select" value={reaction} onChange={e => setReaction(e.target.value)}>
              {REACTIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select></label>
        </div>
        <div className="btn-row mt-md">
          <button type="button" className="btn accent" onClick={add} disabled={busy}>Add to Queue</button>
          <label className="check"><input type="checkbox" checked={reactOnly} onChange={e => setReactOnly(e.target.checked)} /> React only (no share)</label>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">Queue</h2>
          <span className="muted small">{queue.length} item{queue.length === 1 ? '' : 's'}, {runnable} to run</span>
        </div>
        <div className="table-wrap mt-sm">
          <table className="table">
            <thead>
              <tr><th className="col-no">#</th><th>Profile</th><th>Action</th><th>Post URL</th><th>Comment</th><th>Status</th></tr>
            </thead>
            <tbody>
              {queue.map((q, i) => (
                <tr key={q.id} className={picked === q.id ? 'checked' : ''} tabIndex={0}
                    onClick={() => setPicked(picked === q.id ? null : q.id)}
                    onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); setPicked(picked === q.id ? null : q.id) } }}>
                  <td className="col-no">{i + 1}</td>
                  <td>{q.profile}</td>
                  <td>{q.action}</td>
                  <td className="muted">{q.url}</td>
                  <td className="muted">{q.comment}</td>
                  <td className={'status ' + STATUS[q.status].kind}>{STATUS[q.status].text}</td>
                </tr>
              ))}
              {queue.length === 0 && (
                <tr><td className="empty" colSpan={6}>Queue is empty. Add a share above or load the saved presets.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="btn-row mt-md">
          <button type="button" className="btn" onClick={loadPresets} disabled={busy || n === 0}>Load All Presets</button>
          <button type="button" className="btn" onClick={remove} disabled={busy || picked === null}>Remove Item</button>
          <button type="button" className="btn" onClick={clearAll} disabled={busy || queue.length === 0}>Clear All</button>
          <button type="button" className="btn accent" onClick={onStart} disabled={busy || runnable === 0}>
            {run.active && run.kind === 'queue' ? 'Running…' : 'Start Queue'}
          </button>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">Watch a post</h2>
        <div className="btn-row mt-md">
          <label className="inline"><span className="muted">Watch URL</span>
            <input className="input" style={{ width: 320 }} value={watchUrl} onChange={e => setWatchUrl(e.target.value)} placeholder="https://www.facebook.com/..." /></label>
          <label className="inline"><span className="muted">for</span>
            <input className="input" type="number" min={1} style={{ width: 64 }} value={minutes} onChange={e => setMinutes(e.target.value)} />
            <span className="muted">min</span></label>
          <button type="button" className="btn" disabled={busy || watching || !watchUrl.trim()}
                  onClick={() => { setWatching(true); log('info', `Watching ${watchUrl.trim()} for ${minutes} min on ${n} profile(s)`) }}>
            Watch (active profiles)
          </button>
          <button type="button" className="btn" disabled={!watching} onClick={() => { setWatching(false); log('info', 'Watch stopped') }}>Stop</button>
        </div>
        <div className="radio-row mt-md">
          <span className="muted">Browser mode</span>
          <label className="check"><input type="radio" name="mode" checked={mode === 'headless'} onChange={() => setMode('headless')} /> Headless</label>
          <label className="check"><input type="radio" name="mode" checked={mode === 'visible'} onChange={() => setMode('visible')} /> Visible</label>
        </div>
      </section>
    </div>
  )
}
