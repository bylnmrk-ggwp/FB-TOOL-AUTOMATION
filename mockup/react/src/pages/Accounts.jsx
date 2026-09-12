import { useMemo, useState } from 'react'
import { statusOf } from '../data.js'

const FILTERS = ['All', 'Logged in', 'Needs login', 'Pending', 'Disabled']
const CHECKED = '☑', UNCHECKED = '☐'
const read = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v } catch { return d } }
const write = (k, v) => { try { localStorage.setItem(k, v) } catch { /* ignore */ } }

const passes = (kind, mode) =>
  mode === 'All' ||
  (mode === 'Logged in' && kind === 'ok') ||
  (mode === 'Needs login' && (kind === 'off' || kind === 'pending' || kind === 'warn' || kind === 'running')) ||
  (mode === 'Pending' && (kind === 'pending' || kind === 'running')) ||
  (mode === 'Disabled' && kind === 'disabled')

export default function Accounts({ accounts, selected, setSelected, run, onLoginSelected, log }) {
  const [search, setSearch] = useState(() => read('fbtool.accountsSearch', ''))
  const [filter, setFilter] = useState(() => {
    const f = read('fbtool.accountsFilter', 'All')
    return FILTERS.includes(f) ? f : 'All'
  })
  const [status, setStatus] = useState({ text: 'No profile loaded', ok: false })
  const [setupStatus, setSetupStatus] = useState('')

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return accounts
      .map(a => ({ ...a, st: statusOf(a) }))
      .filter(r => (!needle || `${r.fbName} ${r.username} ${r.gmail} ${r.profile}`.toLowerCase().includes(needle)) && passes(r.st.kind, filter))
  }, [accounts, search, filter])

  const visible = rows.map(r => r.username)
  const allChecked = visible.length > 0 && visible.every(u => selected.has(u))
  const toggle = (u) => setSelected(s => { const n = new Set(s); if (n.has(u)) n.delete(u); else n.add(u); return n })
  const selectAll = () => setSelected(s => new Set([...s, ...visible]))
  const clear = () => setSelected(new Set())
  const toggleAll = () => allChecked
    ? setSelected(s => { const n = new Set(s); visible.forEach(u => n.delete(u)); return n })
    : selectAll()

  const checked = accounts.filter(a => selected.has(a.username))
  const profiles = checked.filter(a => a.profile).map(a => a.profile)
  const one = profiles.length === 1
  const acct = checked.length === 1 ? checked[0] : null
  const busy = run.active
  const off = (cond) => busy || !cond   // disabled flag, like st() in _update_buttons

  const say = (text, ok = false) => setStatus({ text, ok })
  const mock = (label) => { say(`${label}: not wired in the mockup`); log('info', `${label} pressed (mockup)`) }

  const loginSelected = () => {
    const usernames = checked.filter(a => a.profile && a.sheetStatus !== 'DISABLED').map(a => a.username)
    if (usernames.length === 0) { say('None of the checked rows has a Brave profile'); return }
    const skipped = checked.length - usernames.length
    say(`Logging in ${usernames.length} account${usernames.length === 1 ? '' : 's'}${skipped ? `, ${skipped} skipped (no Brave profile)` : ''}…`)
    onLoginSelected(usernames)
  }
  const checkLogin = () => {
    say('Checking login status…')
    log('info', `Check login status: ${profiles.length ? `${profiles.length} checked profile(s)` : 'every saved profile'}`)
  }

  return (
    <div className="accounts">
      <div className="toolbar">
        <label className="inline">
          <span className="muted">Search</span>
          <input className="input" style={{ width: 240 }} value={search} placeholder="name, username, profile, gmail"
                 onChange={e => { setSearch(e.target.value); write('fbtool.accountsSearch', e.target.value) }} />
        </label>
        <label className="inline">
          <span className="muted">Show</span>
          <select className="select" value={filter} onChange={e => { setFilter(e.target.value); write('fbtool.accountsFilter', e.target.value) }}>
            {FILTERS.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <button type="button" className="btn" onClick={selectAll}>Select all</button>
        <button type="button" className="btn" onClick={clear}>Clear</button>
        <span className="spacer" />
        <span className="muted small">
          {rows.length} of {accounts.length} row{accounts.length === 1 ? '' : 's'}{selected.size ? ` · ${selected.size} selected` : ''}
        </span>
      </div>

      <div className="table-wrap">
        <table className="table accounts-table">
          <thead>
            <tr>
              <th className="col-check">
                <button type="button" className="check-btn" onClick={toggleAll} aria-label={allChecked ? 'Clear visible rows' : 'Select visible rows'}>
                  {allChecked ? CHECKED : UNCHECKED}
                </button>
              </th>
              <th className="col-no">#</th>
              <th>Name</th>
              <th>Username</th>
              <th>Brave profile</th>
              <th>Status</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const on = selected.has(r.username)
              return (
                <tr key={r.username} className={on ? 'checked' : ''} tabIndex={0} aria-selected={on}
                    onClick={() => toggle(r.username)}
                    onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggle(r.username) } }}>
                  <td className="col-check"><span className="check" aria-hidden="true">{on ? CHECKED : UNCHECKED}</span></td>
                  <td className="col-no">{r.no}</td>
                  <td>{r.fbName}</td>
                  <td>{r.username}</td>
                  <td className={r.profile ? '' : 'muted'}>{r.profile || '—'}</td>
                  <td className={'status ' + r.st.kind}>{r.st.text}</td>
                  <td className="muted">{r.reason}</td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr><td className="empty" colSpan={7}>No rows match. Clear the search or pick another filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="actions">
        <button type="button" className="btn accent" disabled={off(checked.length > 0)} onClick={loginSelected}>Log in selected</button>
        <button type="button" className="btn" disabled={busy} onClick={checkLogin}>Check login status</button>
        <button type="button" className="btn" disabled={off(profiles.length > 0)} onClick={() => mock('Auto setup')}>Auto setup</button>
        <button type="button" className="btn" disabled={off(profiles.length > 0)} onClick={() => mock('Accept friend requests')}>Accept friend requests</button>
        <button type="button" className="btn" disabled={busy} onClick={() => mock('Update FB names')}>Update FB names</button>
        <button type="button" className="btn" disabled={busy} onClick={() => mock('Add Brave profile')}>+ Add Brave profile</button>
        <button type="button" className="btn" disabled={busy} onClick={() => say('Scan done: nothing new')}>Scan for new profiles</button>
        <button type="button" className="btn" disabled={off(one)} onClick={() => say(`Launching '${profiles[0]}'…`, true)}>Launch</button>
        <button type="button" className="btn" disabled={off(one)} onClick={() => mock('Update FB name')}>Update FB name</button>
        <button type="button" className="btn" disabled={off(one)} onClick={() => setSetupStatus(`Running auto setup on '${profiles[0]}'…`)}>Auto setup (one)</button>
        <button type="button" className="btn" disabled={off(one)} onClick={() => mock('Remove')}>Remove</button>
        <button type="button" className="btn" disabled={off(acct !== null && !acct.profile)} onClick={() => mock('Link to Brave profile')}>Link to Brave profile{'…'}</button>
        <button type="button" className="btn" disabled={off(acct !== null && !!acct.profile)} onClick={() => mock('Unlink')}>Unlink</button>
      </div>

      <div className="foot">
        <span className={'dot' + (status.ok ? ' ok' : '')} aria-hidden="true">{'●'}</span>
        <span>{status.text}</span>
        {setupStatus && <span className="setup">{setupStatus}</span>}
      </div>
    </div>
  )
}
