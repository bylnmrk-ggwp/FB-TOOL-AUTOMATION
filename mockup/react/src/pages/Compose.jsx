import { useState } from 'react'
import { GROUPS, PRESETS, RECENT_SHARES } from '../data.js'

const REACTIONS = ['None', 'Like', 'Love', 'Care', 'Haha', 'Wow']

export default function Compose({ scope, run, log }) {
  const [url, setUrl] = useState('')
  const [group, setGroup] = useState(GROUPS[0].name)
  const [reaction, setReaction] = useState('Like')
  const [comments, setComments] = useState('Available for viewing this weekend\nStill available? Message us')
  const [joinUrls, setJoinUrls] = useState('')
  const [groups, setGroups] = useState(GROUPS)
  const [presets, setPresets] = useState(PRESETS)
  const [presetPicked, setPresetPicked] = useState(null)
  const busy = run.active
  const n = scope.length
  const checkedGroups = groups.filter(g => g.checked)

  const share = (label, target) => {
    if (!url.trim()) { log('error', `✗ ${label}: Post URL is empty`); return }
    log('ok', `✓ ${label}: queued for ${n} profile${n === 1 ? '' : 's'} (${target})`)
  }
  const savePreset = () => {
    const name = `Preset ${presets.length + 1}${url.trim() ? ` - ${url.trim().slice(-10)}` : ''}`
    setPresets(p => [...p, name])
    log('info', `Saved preset "${name}"`)
  }
  const deletePreset = () => {
    if (presetPicked === null) return
    setPresets(p => p.filter(x => x !== presetPicked))
    log('info', `Deleted preset "${presetPicked}"`)
    setPresetPicked(null)
  }
  const toggleGroup = (id) => setGroups(gs => gs.map(g => g.id === id ? { ...g, checked: !g.checked } : g))
  const setAll = (checked) => setGroups(gs => gs.map(g => ({ ...g, checked })))
  const joinAll = () => {
    const urls = joinUrls.split('\n').map(s => s.trim()).filter(Boolean)
    log('info', `Join All Groups: ${urls.length} group${urls.length === 1 ? '' : 's'} on ${n} profile${n === 1 ? '' : 's'}`)
    setJoinUrls('')
  }

  return (
    <div className="compose">
      <div className="col">
        <section className="card">
          <h2 className="card-title">Share to Group</h2>
          <div className="form-grid mt-md">
            <label className="field wide"><span>Post URL</span>
              <input className="input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.facebook.com/..." /></label>
            <label className="field"><span>Group</span>
              <select className="select" value={group} onChange={e => setGroup(e.target.value)}>
                {groups.map(g => <option key={g.id} value={g.name}>{g.name}</option>)}
              </select></label>
            <label className="field"><span>Reaction</span>
              <select className="select" value={reaction} onChange={e => setReaction(e.target.value)}>
                {REACTIONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select></label>
            <label className="field wide"><span>Comments (one per line, one is picked at random)</span>
              <textarea className="textarea" rows={4} value={comments} onChange={e => setComments(e.target.value)} /></label>
          </div>
          <div className="btn-row mt-md">
            <button type="button" className="btn accent" disabled={busy || n === 0} onClick={() => share('Share to Timeline', 'timeline')}>Share to Timeline</button>
            <button type="button" className="btn" disabled={busy || n === 0} onClick={() => share('Share to Group', group)}>Share to Group</button>
            <button type="button" className="btn" disabled={busy || n === 0 || checkedGroups.length === 0}
                    onClick={() => share('Share Selected Groups', `${checkedGroups.length} group${checkedGroups.length === 1 ? '' : 's'}`)}>
              Share Selected Groups
            </button>
            <button type="button" className="btn" onClick={() => log('info', 'New Timeline Post: composer dialog (mockup)')}>New Timeline Post{'…'}</button>
            <button type="button" className="btn" onClick={savePreset}>Save Preset</button>
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">Join Group (Bulk)</h2>
          <label className="field mt-md"><span>Group URLs (one per line)</span>
            <textarea className="textarea" rows={4} value={joinUrls} onChange={e => setJoinUrls(e.target.value)} placeholder="https://www.facebook.com/groups/..." /></label>
          <div className="btn-row mt-md">
            <button type="button" className="btn" disabled={busy || n === 0 || !joinUrls.trim()} onClick={joinAll}>Join All Groups</button>
            <span className="muted small">{n} profile{n === 1 ? '' : 's'} in scope</span>
          </div>
        </section>
      </div>

      <div className="col">
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">My Groups</h2>
            <span className="muted small">{checkedGroups.length} of {groups.length} selected</span>
          </div>
          <ul className="group-list">
            {groups.map(g => (
              <li key={g.id}>
                <label className="check"><input type="checkbox" checked={g.checked} onChange={() => toggleGroup(g.id)} /> {g.name}</label>
                <span className="muted small">{g.members}</span>
              </li>
            ))}
          </ul>
          <div className="btn-row">
            <button type="button" className="btn sm" onClick={() => setAll(true)}>Select All</button>
            <button type="button" className="btn sm" onClick={() => setAll(false)}>Deselect All</button>
            <span className="spacer" />
            <button type="button" className="btn sm" disabled={busy} onClick={() => log('info', 'Fetch My Groups started (mockup)')}>Fetch My Groups</button>
            <button type="button" className="btn sm" onClick={() => log('info', 'Loaded saved groups')}>Load Saved</button>
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">Recent Shares</h2>
          <ul className="plain-list">
            {RECENT_SHARES.map((s, i) => (
              <li key={i}>
                <span className={s.ok ? 'ok' : 'err'} aria-hidden="true">{s.ok ? '✓' : '✗'}</span>
                <span className="muted">{s.time}</span>
                <span>{s.profile}</span>
                <span className="muted">to {s.target}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <div className="card-head">
            <h2 className="card-title">Saved Presets</h2>
            <button type="button" className="btn sm" disabled={presetPicked === null} onClick={deletePreset}>Delete</button>
          </div>
          <ul className="plain-list">
            {presets.map(p => (
              <li key={p}>
                <label className="check"><input type="radio" name="preset" checked={presetPicked === p} onChange={() => setPresetPicked(p)} /> {p}</label>
              </li>
            ))}
            {presets.length === 0 && <li className="muted">No presets saved. Fill in a share and press Save Preset.</li>}
          </ul>
        </section>
      </div>
    </div>
  )
}
