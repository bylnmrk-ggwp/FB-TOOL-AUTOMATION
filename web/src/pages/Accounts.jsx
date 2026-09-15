import { useMemo, useState } from 'react'
import { useStore, actions, rowKey } from '../store.js'

const FILTERS = ['All', 'Logged in', 'Needs login', 'Pending', 'Disabled']
const CHECKED = '☑', UNCHECKED = '☐'
const LS = { search: 'fbtool.accountsSearch', filter: 'fbtool.accountsFilter' }
const read = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v } catch { return d } }
const write = (k, v) => { try { localStorage.setItem(k, v) } catch { /* private window: nothing to persist to */ } }

// Same precedence as the Tk AccountsPage: a disabled account first, then
// the share restriction, then the live verdict of a running scan/login,
// then the stored verdict. A row with no recorded status has never been
// attempted, which is what 'Pending' means. A Brave profile no roster row
// links to has no account to be logged in as, so it is its own kind.
export function statusOf(a) {
  if (a.status === 'disabled') return { kind: 'disabled', text: '✕ Disabled' }
  if (a.restricted) return { kind: 'warn', text: '⚠ Restricted' }
  const loggedIn = a.live === undefined ? a.logged_in : a.live
  if (loggedIn) return { kind: 'ok', text: '● Logged in' }
  if (a.username === null || a.username === undefined) return { kind: 'off', text: '○ No account' }
  if (!a.status) return { kind: 'pending', text: '○ Pending' }
  return { kind: 'off', text: '○ Not logged in' }
}

const passes = (kind, mode) =>
  mode === 'All' ||
  (mode === 'Logged in' && kind === 'ok') ||
  (mode === 'Needs login' && (kind === 'off' || kind === 'pending' || kind === 'warn' || kind === 'running')) ||
  (mode === 'Pending' && (kind === 'pending' || kind === 'running')) ||
  (mode === 'Disabled' && kind === 'disabled')

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

export default function Accounts() {
  const accounts = useStore(s => s.accounts)
  const selected = useStore(s => s.selected)
  const server = useStore(s => s.server)

  const [search, setSearch] = useState(() => read(LS.search, ''))
  const [filter, setFilter] = useState(() => {
    const f = read(LS.filter, 'All')
    return FILTERS.includes(f) ? f : 'All'
  })
  const [status, setStatus] = useState({ text: 'Tick rows, then pick an action', ok: false })
  const [linking, setLinking] = useState(null)   // {username, profile} while the Link… picker is open

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return accounts
      .map(a => ({ ...a, key: rowKey(a), st: statusOf(a) }))
      .filter(r => (
        (!needle || `${r.facebook_name} ${r.username ?? ''} ${r.gmail} ${r.linked_profile}`.toLowerCase().includes(needle))
        && passes(r.st.kind, filter)))
  }, [accounts, search, filter])

  const visible = rows.map(r => r.key)
  const allChecked = visible.length > 0 && visible.every(k => selected.has(k))
  const selectAll = () => actions.setSelected([...selected, ...visible])
  const toggleAll = () => allChecked
    ? actions.setSelected([...selected].filter(k => !visible.includes(k)))
    : selectAll()

  const checked = accounts.filter(a => selected.has(rowKey(a)))
  const profiles = checked.filter(a => a.linked_profile).map(a => a.linked_profile)
  const one = profiles.length === 1
  const acct = checked.length === 1 ? checked[0] : null
  const hasUsername = acct !== null && acct.username !== null && acct.username !== undefined
  const unlinkedProfiles = accounts.filter(a => (a.username === null || a.username === undefined) && a.linked_profile).map(a => a.linked_profile)

  // Every action here drives Brave on the PC, and the worker runs one thing
  // at a time; the server answers 409 anyway, but a disabled button says
  // it first.
  const busy = !!(server?.login_run_active || server?.scan_active || server?.run)
  const off = (cond) => busy || !cond
  const say = (text, ok = false) => setStatus({ text, ok })

  // Roster rows with no Brave profile: they cannot be logged in until one
  // exists, which is what Provision creates.
  const unprovisioned = accounts.filter(a => a.username && !a.linked_profile).length
  const provisioning = !!server?.provision_active
  // Checked rows that cannot be logged in yet because they have no profile.
  const needSetup = checked.filter(a => a.username && !a.linked_profile)
  const setupAndLogin = async () => {
    const names = needSetup.map(a => a.username)
    if (!window.confirm(
      `Create Brave profiles for ${names.length} selected account${names.length === 1 ? '' : 's'} `
      + 'and log them in?\n\nEvery Brave window must be closed first.')) return
    say('Setting up profiles, then logging in…', true)
    if (await actions.setupAndLogin(names)) say('Setup started — watch the Log page', true)
  }

  const provision = async () => {
    if (!window.confirm(
      `Create a browser profile for ${unprovisioned} account${unprovisioned === 1 ? '' : 's'} on the PC?\n\n`
      + 'The PC uses whichever browser it is set to. On Brave every Brave window '
      + 'must be closed first, or the new profiles are discarded.')) return
    say('Creating profiles on the PC…', true)
    if (await actions.provisionProfiles()) say('Provisioning started — watch the Log page', true)
  }
  const fire = async (promise, doing) => {
    say(doing, true)
    const ok = await promise
    if (!ok) say('The PC refused the request (see the message at the corner)')
  }

  const loginSelected = () => {
    const usernames = checked.filter(a => a.username && a.linked_profile && a.status !== 'disabled').map(a => a.username)
    if (usernames.length === 0) { say('None of the checked rows has a Brave profile to log in with'); return }
    const skipped = checked.length - usernames.length
    const note = skipped ? `\n${plural(skipped, 'row')} skipped (no Brave profile or disabled).` : ''
    if (!window.confirm(`Log in ${plural(usernames.length, 'account')}?${note}\n\nThis opens Brave on the PC for each one, in turn.`)) return
    fire(actions.loginSelected(usernames), `Logging in ${plural(usernames.length, 'account')}…`)
  }
  // Every account that could be driven but is not logged in right now: the
  // bulk retry after a run where Facebook gated most of the roster. Scope is
  // the whole table, not the ticked rows, so it needs no selection.
  const notLoggedIn = accounts.filter(a => a.username && a.linked_profile
    && (a.live ?? a.logged_in) !== true
    && (a.status || '').toLowerCase() !== 'disabled')
  const reloginFailed = () => {
    const usernames = notLoggedIn.map(a => a.username)
    if (usernames.length === 0) { say('Every account with a profile is already logged in'); return }
    if (!window.confirm(
      `Re-login ${plural(usernames.length, 'account')} that are not logged in?`
      + '\n\nBrave must be closed. They run in batches of 5 with a pause between.')) return
    fire(actions.loginSelected(usernames), `Re-logging in ${plural(usernames.length, 'account')}…`)
  }

  const checkLogin = () => {
    const names = profiles.length ? profiles : null
    fire(actions.checkLogin(names), `Checking login status of ${names ? plural(names.length, 'profile') : 'every Brave profile'}…`)
  }
  const autoSetup = () => {
    if (!window.confirm(`Run auto setup on ${plural(profiles.length, 'profile')}?\n\nThis drives Brave on the PC and may ask you to pick a profile picture.`)) return
    fire(actions.autoSetupAll(profiles), `Auto setup on ${plural(profiles.length, 'profile')}…`)
  }
  const acceptPending = () => {
    if (!window.confirm(`Accept every pending friend request on ${plural(profiles.length, 'profile')}?`)) return
    fire(actions.acceptPending(profiles), `Accepting friend requests on ${plural(profiles.length, 'profile')}…`)
  }
  const launch = () => {
    const name = profiles[0]
    if (!window.confirm(`Launch '${name}'?\n\nThis opens a Brave window on the PC, not on this device.`)) return
    fire(actions.launch(name), `Launching '${name}' on the PC…`)
  }
  const unlink = async () => {
    if (!window.confirm(`Unlink '${acct.linked_profile}' from ${acct.username}?\n\nThe Brave profile stays on the PC; only the roster link is removed.`)) return
    say(`Unlinking ${acct.username}…`, true)
    if (await actions.unlink(acct.username)) say(`Unlinked ${acct.username}`, true)
  }
  const openLink = () => {
    if (unlinkedProfiles.length === 0) { say('Every Brave profile is already linked to an account'); return }
    setLinking({ username: acct.username, profile: unlinkedProfiles[0] })
  }
  const confirmLink = async () => {
    const { username, profile } = linking
    setLinking(null)
    say(`Linking ${username} to '${profile}'…`, true)
    if (await actions.link(username, profile)) say(`Linked ${username} to '${profile}'`, true)
  }

  return (
    <div className="accounts">
      <div className="toolbar">
        <label className="inline">
          <span className="muted">Search</span>
          <input className="input search" value={search} placeholder="name, username, profile, gmail"
                 onChange={e => { setSearch(e.target.value); write(LS.search, e.target.value) }} />
        </label>
        <label className="inline">
          <span className="muted">Show</span>
          <select className="select" value={filter} onChange={e => { setFilter(e.target.value); write(LS.filter, e.target.value) }}>
            {FILTERS.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <button type="button" className="btn" onClick={selectAll} disabled={visible.length === 0}>Select all</button>
        <button type="button" className="btn" onClick={actions.clearSelected} disabled={selected.size === 0}>Clear</button>
        <span className="spacer" />
        <span className="muted small">
          {rows.length} of {plural(accounts.length, 'row')}{selected.size ? ` · ${selected.size} selected` : ''}
        </span>
      </div>

      <div className="table-wrap">
        <table className="table accounts-table">
          <thead>
            <tr>
              <th className="col-check">
                <button type="button" className="check-btn" onClick={toggleAll} disabled={visible.length === 0}
                        aria-label={allChecked ? 'Clear visible rows' : 'Select visible rows'}>
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
              const on = selected.has(r.key)
              return (
                <tr key={r.key} className={on ? 'checked' : ''} tabIndex={0} aria-selected={on}
                    onClick={() => actions.toggleSelected(r.key)}
                    onKeyDown={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); actions.toggleSelected(r.key) } }}>
                  <td className="col-check"><span className="check" aria-hidden="true">{on ? CHECKED : UNCHECKED}</span></td>
                  <td className="col-no">{r.sheet_no ?? ''}</td>
                  <td className={r.facebook_name ? '' : 'muted'}>{r.facebook_name || '—'}</td>
                  <td className={r.username ? '' : 'muted'}>{r.username || '—'}</td>
                  <td className={r.linked_profile ? '' : 'muted'}>{r.linked_profile || '—'}</td>
                  <td className={'status ' + r.st.kind}>{r.st.text}</td>
                  <td className="muted">{r.status_reason}</td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr><td className="empty" colSpan={7}>
                {accounts.length === 0 ? 'No accounts yet. The roster comes from the Google Sheet.' : 'No rows match. Clear the search or pick another filter.'}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="actions">
        <button type="button" className="btn accent" disabled={off(checked.length > 0)} onClick={loginSelected}>Log in selected</button>
        {notLoggedIn.length > 0 && (
          <button type="button" className="btn" disabled={busy} onClick={reloginFailed}
                  title="Re-runs the login for every account with a Brave profile that is not logged in">
            Re-login not logged in ({notLoggedIn.length})
          </button>
        )}
        <button type="button" className="btn" disabled={busy} onClick={checkLogin}
                title={profiles.length ? `Check ${plural(profiles.length, 'checked profile')}` : 'Check every Brave profile'}>Check login status</button>
        <button type="button" className="btn" disabled={off(profiles.length > 0)} onClick={autoSetup}>Auto setup</button>
        <button type="button" className="btn" disabled={off(profiles.length > 0)} onClick={acceptPending}>Accept friend requests</button>
        <button type="button" className="btn" disabled={off(one)} onClick={launch} title="Opens a Brave window on the PC">Launch</button>
        {needSetup.length > 0 && (
          <button type="button" className="btn accent" disabled={busy || provisioning} onClick={setupAndLogin}
                  title="Creates the Brave profile for each selected account, then logs it in">
            Set up &amp; log in ({needSetup.length})
          </button>
        )}
        {unprovisioned > 0 && (
          <button type="button" className="btn accent" disabled={busy || provisioning} onClick={provision}
                  title="Creates and links a browser profile for every account that has none">
            {provisioning ? 'Creating profiles…' : `Provision ${unprovisioned} profile${unprovisioned === 1 ? '' : 's'}`}
          </button>
        )}
        <button type="button" className="btn" disabled={off(hasUsername && !acct.linked_profile)} onClick={openLink}>Link{'…'}</button>
        <button type="button" className="btn" disabled={off(hasUsername && !!acct.linked_profile)} onClick={unlink}>Unlink</button>
      </div>

      <div className="foot">
        <span className={'dot' + (status.ok ? ' ok' : '')} aria-hidden="true">{'●'}</span>
        <span>{busy ? 'A run is active on the PC — actions resume when it finishes' : status.text}</span>
      </div>

      {linking && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="link-title">
          <div className="modal card link-picker">
            <h2 id="link-title" className="card-title">Link {linking.username}</h2>
            <p className="muted small mt-xs">Pick the Brave profile this account signs in from. Only profiles no other row uses are listed.</p>
            <label className="field mt-md">
              <span>Brave profile</span>
              <select className="select" value={linking.profile} onChange={e => setLinking({ ...linking, profile: e.target.value })}>
                {unlinkedProfiles.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <div className="btn-row mt-md">
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setLinking(null)}>Cancel</button>
              <button type="button" className="btn accent" onClick={confirmLink}>Link</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
