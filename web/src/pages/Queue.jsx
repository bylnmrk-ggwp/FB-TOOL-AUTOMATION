import { useState } from 'react'
import { useStore, actions, rowKey } from '../store.js'

// The share queue, live. The list itself lives on the PC (AppState.queue), so
// this page never edits it locally: every button calls a route and the state
// event that follows carries the new list back to every open device.
//
// Scope comes from the rows ticked on the Accounts page - the same "one item
// per profile" fan-out the Tk quick-add did. With nothing ticked there is no
// scope to add for, so Add says so rather than queueing nothing.
const REACTIONS = ['Like', 'Love', 'Care', 'Haha', 'Wow']
const ACTIONS = [
  { key: 'group', label: 'Share to group' },
  { key: 'timeline', label: 'Share to timeline' },
  { key: 'react', label: 'React only' },
  { key: 'comment', label: 'Comment only' },
  { key: 'post_text', label: 'Text post' },
]

export default function Queue() {
  const accounts = useStore(s => s.accounts)
  const selected = useStore(s => s.selected)
  const queue = useStore(s => s.queue)
  const server = useStore(s => s.server)

  const [actionType, setActionType] = useState('group')
  const [url, setUrl] = useState('')
  const [groupName, setGroupName] = useState('')
  const [comment, setComment] = useState('')
  const [reaction, setReaction] = useState('Like')
  const [text, setText] = useState('')
  const [watchUrl, setWatchUrl] = useState('')
  const [minutes, setMinutes] = useState(10)
  const [busy, setBusy] = useState(false)

  // Ticked rows that actually have a Brave profile: only those can drive one.
  const scope = accounts.filter(a => selected.has(rowKey(a)) && a.linked_profile)
  const scopeNames = scope.map(a => a.linked_profile)

  const run = server?.run ?? null
  const running = !!run || !!server?.login_run_active || !!server?.scan_active
  const batch = run && run.kind === 'batch' ? run : null
  const needsUrl = actionType !== 'post_text'
  const canAdd = scopeNames.length > 0 && !busy && !running
    && (needsUrl ? url.trim().startsWith('http') : text.trim().length > 0)
    && (actionType !== 'group' || groupName.trim().length > 0)

  const wrap = async (fn) => { setBusy(true); try { await fn() } finally { setBusy(false) } }

  const add = () => wrap(() => actions.queueAdd({
    profile_names: scopeNames,
    action_type: actionType,
    post_url: needsUrl ? url.trim() : null,
    group_name: actionType === 'group' ? groupName.trim() : null,
    comment_text: comment.trim() || null,
    reaction: actionType === 'react' || actionType === 'group' ? reaction.toLowerCase() : null,
    text: actionType === 'post_text' ? text : null,
  }))

  const start = () => {
    if (!queue.length) return
    if (!window.confirm(`Run ${queue.length} queued item${queue.length === 1 ? '' : 's'} on the PC now?`)) return
    wrap(actions.queueRun)
  }
  const clear = () => {
    if (!queue.length) return
    if (!window.confirm(`Remove all ${queue.length} queued items?`)) return
    wrap(actions.queueClear)
  }
  const watch = () => {
    if (!watchUrl.trim().startsWith('http')) return
    if (!window.confirm('This opens a visible Brave window per active profile on the PC. Continue?')) return
    wrap(() => actions.queueWatch({
      url: watchUrl.trim(),
      minutes: Number(minutes) > 0 ? Number(minutes) : null,
      profile_names: scopeNames.length ? scopeNames : null,
    }))
  }

  return (
    <div className="queue">
      <div>
        <h2 className="card-title">Share Queue</h2>
        <p className="muted small mt-xs">
          Every item carries its own profile. Build the list here, then run it on the PC.
        </p>
      </div>

      <div>
        <div className="muted small">Profile scope</div>
        <div className="profile-strip mt-xs">
          {scopeNames.length
            ? <span className="small">{scopeNames.length} profile{scopeNames.length === 1 ? '' : 's'} ticked: {scopeNames.slice(0, 6).join(', ')}{scopeNames.length > 6 ? ` +${scopeNames.length - 6}` : ''}</span>
            : <span className="muted small">Nothing ticked. Choose profiles on the Accounts page first.</span>}
        </div>
      </div>

      <section className="card">
        <h2 className="card-title">Quick Add</h2>
        <p className="muted small mt-xs">One item is queued per ticked profile.</p>
        <div className="form-grid mt-md">
          <label className="field"><span>Command</span>
            <select className="select" value={actionType} onChange={e => setActionType(e.target.value)}>
              {ACTIONS.map(a => <option key={a.key} value={a.key}>{a.label}</option>)}
            </select></label>
          {needsUrl && (
            <label className="field wide"><span>Post URL</span>
              <input className="input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.facebook.com/..." /></label>
          )}
          {actionType === 'group' && (
            <label className="field"><span>Group name</span>
              <input className="input" value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="exact group name" /></label>
          )}
          {actionType === 'post_text' && (
            <label className="field wide"><span>Text</span>
              <textarea className="textarea" rows={3} value={text} onChange={e => setText(e.target.value)} /></label>
          )}
          <label className="field"><span>Comment</span>
            <input className="input" value={comment} onChange={e => setComment(e.target.value)} placeholder="optional" /></label>
          <label className="field"><span>Reaction</span>
            <select className="select" value={reaction} onChange={e => setReaction(e.target.value)}>
              {REACTIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select></label>
        </div>
        <div className="btn-row mt-md">
          <button type="button" className="btn accent" disabled={!canAdd} onClick={add}
                  title={scopeNames.length ? '' : 'Tick profiles on the Accounts page first'}>
            Add to Queue{scopeNames.length ? ` (${scopeNames.length})` : ''}
          </button>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">Queue</h2>
          <span className="muted small">
            {queue.length} item{queue.length === 1 ? '' : 's'}
            {batch ? ` · running ${batch.current}/${batch.total}` : ''}
          </span>
        </div>
        <div className="table-wrap mt-sm">
          <table className="table">
            <thead>
              <tr><th className="col-no">#</th><th>Profile</th><th>Action</th><th>Target</th><th>Comment</th><th /></tr>
            </thead>
            <tbody>
              {queue.length === 0
                ? <tr><td className="empty" colSpan={6}>Queue is empty. Tick profiles on Accounts, then add an item above.</td></tr>
                : queue.map((it, i) => (
                  <tr key={it.id}>
                    <td className="col-no">{i + 1}</td>
                    <td>{it.profile_name}</td>
                    <td>{ACTIONS.find(a => a.key === it.action_type)?.label ?? it.action_type}</td>
                    <td className="ellipsis">{it.group_name || it.post_url || it.text || '—'}</td>
                    <td className="ellipsis">{it.comment_text || '—'}</td>
                    <td>
                      <button type="button" className="btn sm" disabled={busy || running}
                              onClick={() => actions.queueRemove(it.id)}>Remove</button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <div className="btn-row mt-md">
          <button type="button" className="btn" disabled={!queue.length || busy || running} onClick={clear}>Clear All</button>
          <button type="button" className="btn accent" disabled={!queue.length || busy || running} onClick={start}>
            {batch ? `Running ${batch.current}/${batch.total}…` : 'Start Queue'}
          </button>
          {running && !batch && <span className="muted small">Another run is active.</span>}
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">Watch a post</h2>
        <p className="muted small mt-xs">Opens a visible window per active profile on the PC.</p>
        <div className="btn-row mt-md">
          <label className="inline"><span className="muted">Watch URL</span>
            <input className="input" style={{ width: 320 }} value={watchUrl} onChange={e => setWatchUrl(e.target.value)} placeholder="https://www.facebook.com/..." /></label>
          <label className="inline"><span className="muted">for</span>
            <input className="input" type="number" min={1} style={{ width: 64 }} value={minutes} onChange={e => setMinutes(e.target.value)} />
            <span className="muted">min</span></label>
          <button type="button" className="btn" disabled={busy || !watchUrl.trim().startsWith('http')} onClick={watch}>
            Watch{scopeNames.length ? ` (${scopeNames.length})` : ' (active profiles)'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => actions.queueStopWatch()}>Stop</button>
        </div>
      </section>
    </div>
  )
}
