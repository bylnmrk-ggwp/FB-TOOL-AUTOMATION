import { useEffect, useState } from 'react'
import { useStore, actions, rowKey } from '../store.js'

// Share, join and post, live. Scope is the rows ticked on the Accounts page;
// the group list is whatever the PC last fetched from Facebook (GET /api/groups),
// and a fetch rewrites it on the PC, which the ws refetch picks up.
//
// Photos: a phone uploads to the PC first (POST /api/uploads) and the returned
// server-side paths ride into post_to_timeline, which is what the desktop file
// picker used to hand it.
const REACTIONS = ['None', 'Like', 'Love', 'Care', 'Haha', 'Wow']

export default function Compose() {
  const accounts = useStore(s => s.accounts)
  const selected = useStore(s => s.selected)
  const groups = useStore(s => s.groups)
  const groupsLoading = useStore(s => s.groupsLoading)
  const server = useStore(s => s.server)

  const [url, setUrl] = useState('')
  const [group, setGroup] = useState('')
  const [reaction, setReaction] = useState('Like')
  const [comments, setComments] = useState('')
  const [joinUrls, setJoinUrls] = useState('')
  const [picked, setPicked] = useState(() => new Set())
  const [postText, setPostText] = useState('')
  const [images, setImages] = useState([])       // {path, name} from /api/uploads
  const [busy, setBusy] = useState(false)

  useEffect(() => { actions.refreshGroups() }, [])

  const scope = accounts.filter(a => selected.has(rowKey(a)) && a.linked_profile)
  const scopeNames = scope.map(a => a.linked_profile)
  const running = !!server?.run || !!server?.login_run_active || !!server?.scan_active
  const hasUrl = url.trim().startsWith('http')
  const comment = () => {
    const lines = comments.split('\n').map(s => s.trim()).filter(Boolean)
    return lines.length ? lines[Math.floor(Math.random() * lines.length)] : null
  }
  const react = () => (reaction === 'None' ? null : reaction.toLowerCase())
  const blocked = busy || running
  const chosen = groups.filter(g => picked.has(g.url || g.name))

  const wrap = async (fn) => { setBusy(true); try { await fn() } finally { setBusy(false) } }
  const toggle = (key) => setPicked(p => {
    const next = new Set(p)
    if (next.has(key)) next.delete(key); else next.add(key)
    return next
  })
  const setAll = (on) => setPicked(on ? new Set(groups.map(g => g.url || g.name)) : new Set())

  const upload = async (files) => {
    if (!files || !files.length) return
    await wrap(async () => {
      const done = []
      for (const f of files) {
        try { done.push(await actions.uploadImage(f)) } catch { /* the toast says why */ }
      }
      if (done.length) setImages(prev => [...prev, ...done])
    })
  }

  return (
    <div className="compose">
      <div className="col">
        <section className="card">
          <h2 className="card-title">Share to Group</h2>
          <p className="muted small mt-xs">
            {scopeNames.length
              ? `${scopeNames.length} profile${scopeNames.length === 1 ? '' : 's'} ticked on Accounts.`
              : 'Nothing ticked. Bulk actions use every logged-in profile; tick rows on Accounts to narrow it.'}
          </p>
          <div className="form-grid mt-md">
            <label className="field wide"><span>Post URL</span>
              <input className="input" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.facebook.com/..." /></label>
            <label className="field"><span>Group</span>
              <select className="select" value={group} onChange={e => setGroup(e.target.value)}>
                <option value="">{groups.length ? 'Pick a group' : 'No groups fetched yet'}</option>
                {groups.map(g => <option key={g.url || g.name} value={g.name}>{g.name}</option>)}
              </select></label>
            <label className="field"><span>Reaction</span>
              <select className="select" value={reaction} onChange={e => setReaction(e.target.value)}>
                {REACTIONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select></label>
            <label className="field wide"><span>Comments (one per line, one is picked at random)</span>
              <textarea className="textarea" rows={4} value={comments} onChange={e => setComments(e.target.value)} /></label>
          </div>
          <div className="btn-row mt-md">
            <button type="button" className="btn accent" disabled={blocked || !hasUrl}
                    onClick={() => wrap(() => actions.composeShareTimeline({
                      post_url: url.trim(), comment_text: comment(), reaction: react(),
                    }))}>Share to Timeline</button>
            <button type="button" className="btn" disabled={blocked || !hasUrl || !group}
                    onClick={() => wrap(() => actions.composeShare({
                      post_url: url.trim(), group_name: group, comment_text: comment(), reaction: react(),
                    }))}>Share to Group</button>
            <button type="button" className="btn" disabled={blocked || !hasUrl || chosen.length === 0}
                    onClick={() => wrap(() => actions.composeShareBulk({
                      post_url: url.trim(),
                      groups: chosen.map(g => ({ name: g.name, url: g.url, profiles: g.profiles ?? [] })),
                      comment_text: comment(), reaction: react(),
                      profile_names: scopeNames.length ? scopeNames : null,
                    }))}>Share Selected Groups{chosen.length ? ` (${chosen.length})` : ''}</button>
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">Post to Timeline</h2>
          <label className="field mt-md"><span>Text</span>
            <textarea className="textarea" rows={3} value={postText} onChange={e => setPostText(e.target.value)}
                      placeholder="What is on your mind?" /></label>
          <div className="btn-row mt-md">
            <label className="btn sm">
              Add photos
              <input type="file" accept="image/*" multiple hidden
                     onChange={e => { upload([...e.target.files]); e.target.value = '' }} />
            </label>
            <span className="muted small">
              {images.length ? `${images.length} image${images.length === 1 ? '' : 's'}: ${images.map(i => i.name).join(', ')}` : 'optional'}
            </span>
            {images.length > 0 && (
              <button type="button" className="btn sm" onClick={() => setImages([])}>Clear photos</button>
            )}
          </div>
          <div className="btn-row mt-md">
            <button type="button" className="btn accent" disabled={blocked || !postText.trim()}
                    onClick={() => wrap(async () => {
                      await actions.composePostTimeline({ text: postText, image_paths: images.map(i => i.path) })
                      setPostText(''); setImages([])
                    })}>Post to Timeline</button>
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">Join Group (Bulk)</h2>
          <label className="field mt-md"><span>Group URLs (one per line)</span>
            <textarea className="textarea" rows={4} value={joinUrls} onChange={e => setJoinUrls(e.target.value)}
                      placeholder="https://www.facebook.com/groups/..." /></label>
          <div className="btn-row mt-md">
            <button type="button" className="btn"
                    disabled={blocked || !joinUrls.split('\n').some(l => l.trim().startsWith('http'))}
                    onClick={() => wrap(async () => {
                      const urls = joinUrls.split('\n').map(s => s.trim()).filter(u => u.startsWith('http'))
                      const ok = await actions.composeJoin({ urls, profile_names: scopeNames.length ? scopeNames : null })
                      if (ok) setJoinUrls('')
                    })}>Join All Groups</button>
            <span className="muted small">
              {scopeNames.length ? `${scopeNames.length} profile${scopeNames.length === 1 ? '' : 's'}` : 'every logged-in profile'}
            </span>
          </div>
        </section>
      </div>

      <div className="col">
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">My Groups</h2>
            <span className="muted small">{chosen.length} of {groups.length} selected</span>
          </div>
          <ul className="group-list">
            {groups.length === 0
              ? <li className="muted small">{groupsLoading ? 'Loading…' : 'No groups yet. Press Fetch My Groups.'}</li>
              : groups.map(g => (
                <li key={g.url || g.name}>
                  <label className="check">
                    <input type="checkbox" checked={picked.has(g.url || g.name)} onChange={() => toggle(g.url || g.name)} />
                    {g.name}
                  </label>
                  <span className="muted small">{(g.profiles ?? []).length} profile{(g.profiles ?? []).length === 1 ? '' : 's'}</span>
                </li>
              ))}
          </ul>
          <div className="btn-row">
            <button type="button" className="btn sm" disabled={!groups.length} onClick={() => setAll(true)}>Select All</button>
            <button type="button" className="btn sm" disabled={!chosen.length} onClick={() => setAll(false)}>Deselect All</button>
            <span className="spacer" />
            <button type="button" className="btn sm" disabled={blocked}
                    onClick={() => wrap(() => actions.fetchGroups(scopeNames.length ? scopeNames : null))}>
              Fetch My Groups
            </button>
            <button type="button" className="btn sm" disabled={groupsLoading}
                    onClick={() => actions.refreshGroups()}>Reload</button>
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">How this runs</h2>
          <p className="muted small">
            Every button here queues a command on the PC. Progress and failures arrive in the
            Log page and the status bar; nothing runs in this browser.
          </p>
        </section>
      </div>
    </div>
  )
}
