import { useState } from 'react'
import { useStore } from '../store.js'

// Phase-1 preview of the Queue page. The layout and styling match the desktop
// app, but every button that would drive Brave or the share queue is disabled:
// the phase-1 backend exposes no queue routes (see store.js actions), so the
// real work still happens in the Tk app. Form fields are local state so the
// page is explorable; the queue table stays empty because Add is disabled.
const REACTIONS = ['Like', 'Love', 'Care', 'Haha', 'Wow']
const PHASE2 = 'Runs in phase 2 — use the desktop app (python main.py --tk)'

export default function Queue() {
  // Read the roster only to say how many profiles exist; selection lives on the
  // Accounts page and is not shared here, so no live scope is fabricated.
  const accounts = useStore(s => s.accounts)
  const profileCount = accounts.filter(a => a.linked_profile).length

  const [url, setUrl] = useState('')
  const [comment, setComment] = useState('')
  const [reaction, setReaction] = useState('Like')
  const [reactOnly, setReactOnly] = useState(false)
  const [watchUrl, setWatchUrl] = useState('')
  const [minutes, setMinutes] = useState(10)
  const [mode, setMode] = useState('headless')

  return (
    <div className="queue">
      <div className="banner preview">
        Preview — Queue and Compose actions run in the desktop app for now (python main.py --tk). Phase 2 wires them to this web UI.
      </div>

      <div>
        <h2 className="card-title">Share Queue</h2>
        <p className="muted small mt-xs">Load saved presets or add timeline shares {'—'} each item uses its own profile.</p>
      </div>

      <div>
        <div className="muted small">Profile scope</div>
        <div className="profile-strip mt-xs">
          <span className="muted small">Select profiles on the Accounts page{profileCount ? ` (${profileCount} available)` : ''}.</span>
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
          <button type="button" className="btn accent" disabled title={PHASE2}>Add to Queue</button>
          <label className="check"><input type="checkbox" checked={reactOnly} onChange={e => setReactOnly(e.target.checked)} /> React only (no share)</label>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">Queue</h2>
          <span className="muted small">0 items, 0 to run</span>
        </div>
        <div className="table-wrap mt-sm">
          <table className="table">
            <thead>
              <tr><th className="col-no">#</th><th>Profile</th><th>Action</th><th>Post URL</th><th>Comment</th><th>Status</th></tr>
            </thead>
            <tbody>
              <tr><td className="empty" colSpan={6}>The queue runs in the desktop app for now (python main.py --tk).</td></tr>
            </tbody>
          </table>
        </div>
        <div className="btn-row mt-md">
          <button type="button" className="btn" disabled title={PHASE2}>Load All Presets</button>
          <button type="button" className="btn" disabled title={PHASE2}>Remove Item</button>
          <button type="button" className="btn" disabled title={PHASE2}>Clear All</button>
          <button type="button" className="btn accent" disabled title={PHASE2}>Start Queue</button>
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
          <button type="button" className="btn" disabled title={PHASE2}>Watch (active profiles)</button>
          <button type="button" className="btn" disabled title={PHASE2}>Stop</button>
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
