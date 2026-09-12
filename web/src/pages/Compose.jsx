import { useState } from 'react'
import { useStore } from '../store.js'

// Phase-1 preview of the Compose page. Layout and styling match the desktop
// app; every Share / Join / Fetch button is disabled because the phase-1
// backend has no compose or groups routes (see store.js actions). Groups,
// recent shares and presets come from Facebook or the desktop app, so here
// they show real emptiness rather than fabricated rows.
const REACTIONS = ['None', 'Like', 'Love', 'Care', 'Haha', 'Wow']
const PHASE2 = 'Runs in phase 2 — use the desktop app (python main.py --tk)'

export default function Compose() {
  const accounts = useStore(s => s.accounts)
  const profileCount = accounts.filter(a => a.linked_profile).length

  const [url, setUrl] = useState('')
  const [group, setGroup] = useState('')
  const [reaction, setReaction] = useState('Like')
  const [comments, setComments] = useState('Available for viewing this weekend\nStill available? Message us')
  const [joinUrls, setJoinUrls] = useState('')

  // No groups/presets in phase-1 state: these are fetched from Facebook or the
  // desktop app, so the lists are genuinely empty here.
  const groups = []
  const presets = []
  const recentShares = []

  return (
    <div className="compose">
      <div className="col">
        <div className="banner preview">
          Preview — Queue and Compose actions run in the desktop app for now (python main.py --tk). Phase 2 wires them to this web UI.
        </div>

        <section className="card">
          <h2 className="card-title">Share to Group</h2>
          <p className="muted small mt-xs">Select profiles on the Accounts page{profileCount ? ` (${profileCount} available)` : ''}.</p>
          <div className="form-grid mt-md">
            <label className="field wide"><span>Post URL</span>
              <input className="input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.facebook.com/..." /></label>
            <label className="field"><span>Group</span>
              <select className="select" value={group} onChange={e => setGroup(e.target.value)}>
                {groups.length === 0
                  ? <option value="">No groups fetched yet</option>
                  : groups.map(g => <option key={g.id} value={g.name}>{g.name}</option>)}
              </select></label>
            <label className="field"><span>Reaction</span>
              <select className="select" value={reaction} onChange={e => setReaction(e.target.value)}>
                {REACTIONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select></label>
            <label className="field wide"><span>Comments (one per line, one is picked at random)</span>
              <textarea className="textarea" rows={4} value={comments} onChange={e => setComments(e.target.value)} /></label>
          </div>
          <div className="btn-row mt-md">
            <button type="button" className="btn accent" disabled title={PHASE2}>Share to Timeline</button>
            <button type="button" className="btn" disabled title={PHASE2}>Share to Group</button>
            <button type="button" className="btn" disabled title={PHASE2}>Share Selected Groups</button>
            <button type="button" className="btn" disabled title={PHASE2}>New Timeline Post{'…'}</button>
            <button type="button" className="btn" disabled title={PHASE2}>Save Preset</button>
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">Join Group (Bulk)</h2>
          <label className="field mt-md"><span>Group URLs (one per line)</span>
            <textarea className="textarea" rows={4} value={joinUrls} onChange={e => setJoinUrls(e.target.value)} placeholder="https://www.facebook.com/groups/..." /></label>
          <div className="btn-row mt-md">
            <button type="button" className="btn" disabled title={PHASE2}>Join All Groups</button>
            <span className="muted small">Select profiles on the Accounts page</span>
          </div>
        </section>
      </div>

      <div className="col">
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">My Groups</h2>
            <span className="muted small">0 of 0 selected</span>
          </div>
          <ul className="group-list">
            <li className="muted small">No groups yet. Fetch My Groups runs in the desktop app (python main.py --tk).</li>
          </ul>
          <div className="btn-row">
            <button type="button" className="btn sm" disabled title={PHASE2}>Select All</button>
            <button type="button" className="btn sm" disabled title={PHASE2}>Deselect All</button>
            <span className="spacer" />
            <button type="button" className="btn sm" disabled title={PHASE2}>Fetch My Groups</button>
            <button type="button" className="btn sm" disabled title={PHASE2}>Load Saved</button>
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">Recent Shares</h2>
          <ul className="plain-list">
            {recentShares.length === 0 && <li className="muted">No shares yet. Shares run in the desktop app (python main.py --tk).</li>}
          </ul>
        </section>

        <section className="card">
          <div className="card-head">
            <h2 className="card-title">Saved Presets</h2>
            <button type="button" className="btn sm" disabled title={PHASE2}>Delete</button>
          </div>
          <ul className="plain-list">
            {presets.length === 0 && <li className="muted">No presets saved. Presets run in the desktop app (python main.py --tk).</li>}
          </ul>
        </section>
      </div>
    </div>
  )
}
