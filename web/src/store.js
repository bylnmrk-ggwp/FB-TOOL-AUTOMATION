// One store for the whole app. `GET /api/state` seeds it, every WebSocket
// event is folded in by `reduce`, and the UI is a pure function of it. The
// pages (F2) code against PAGES, initialState, useStore, actions and reduce;
// nothing here is renamed without changing the plan.
import { useSyncExternalStore } from 'react'
import * as api from './api.js'
import * as ws from './ws.js'

// Same registry as the Tk MainWindow.PAGES: key, title, Segoe Fluent glyph,
// Unicode fallback for machines without the icon face (every phone).
export const PAGES = [
  { key: 'dashboard', title: 'Dashboard', glyph: '\uE80F', fallback: '▣' },
  { key: 'accounts',  title: 'Accounts',  glyph: '\uE716', fallback: '◉' },
  { key: 'queue',     title: 'Queue',     glyph: '\uE8FD', fallback: '≡' },
  { key: 'compose',   title: 'Compose',   glyph: '\uE70F', fallback: '✎' },
  { key: 'monitor',   title: 'Monitor',   glyph: '\uE9D9', fallback: '◔' },
  { key: 'log',       title: 'Log',       glyph: '\uE7C3', fallback: '▤' },
]

export const MAX_LOG = 2000   // same cap as LogTab.MAX_LINES / LogRing.MAX_LINES

const LS_PAGE = 'fbtool.page'
const read = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v } catch { return d } }
const write = (k, v) => { try { localStorage.setItem(k, v) } catch { /* private window: nothing to persist to */ } }

// ?page=accounts opens a section directly (and lets a screenshot script land
// on a page without clicking); otherwise the last section the operator used.
function initialPage() {
  if (typeof window === 'undefined') return 'dashboard'
  const p = new URLSearchParams(window.location.search).get('page') || read(LS_PAGE, 'dashboard')
  return PAGES.some(x => x.key === p) ? p : 'dashboard'
}

export const initialState = {
  auth: 'unknown',            // 'unknown' | 'in' | 'out'
  connected: false,           // websocket open
  server: null,               // AppState dict from GET /api/state: run, last_run_summary, pending_input, login_run_active, scan_active, system, bridge_alive, version
  counts: null,               // {total, logged_in, pending, pending_unlinked, disabled, profiles, active}
  accounts: [],               // rows from GET /api/accounts (data.accounts_rows keys) + client-only `live` (true/false/undefined from login_scan_progress / login_accounts_progress)
  selected: new Set(),        // usernames (or 'profile:<name>' for unlinked profiles)
  queue: [],                  // AppState.queue: the one batch list, shared by every device, {id, profile_name, action_type, ...}
  groups: [],                 // {name, url, profiles} from GET /api/groups - what the PC last fetched from Facebook
  groupsLoading: false,       // a GET /api/groups in flight, for the My Groups card
  log: [],                    // {stamp, text, level}, max MAX_LOG
  toasts: [],                 // {id, level, text}
  page: initialPage(),        // client-only: the section on screen
}

// The selection key of an accounts row: the username, or 'profile:<name>'
// for a Brave profile no roster row links to (username is null there).
export function rowKey(row) {
  return row.username ?? `profile:${row.linked_profile}`
}

// --- store core -------------------------------------------------------------

let state = initialState
const listeners = new Set()

export function getState() { return state }

export function setState(patch) {
  state = { ...state, ...patch }
  listeners.forEach(fn => fn())
}

export function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

// `selector` must return something referentially stable for an unchanged
// store (a field, not a fresh object or array), or React re-renders forever.
export function useStore(selector = s => s) {
  return useSyncExternalStore(subscribe, () => selector(state), () => selector(state))
}

// Fold one server event into the store. Side effects (refetches) live in
// ws.js so this stays a pure function the proofs can call.
export function dispatch(event) {
  const next = reduce(state, event)
  if (next !== state) { state = next; listeners.forEach(fn => fn()) }
}

// --- toasts -----------------------------------------------------------------

let toastSeq = 0

// The bridge broadcasts {"type":"error"} for a failed result AND the result
// itself carries ok:false, so the same text can arrive twice within a tick;
// an identical toast already on screen is not added again.
function withToast(st, level, text) {
  if (!text || st.toasts.some(t => t.level === level && t.text === text)) return st
  return { ...st, toasts: [...st.toasts, { id: ++toastSeq, level, text }] }
}

function pushToast(level, text) { setState(withToast(state, level, text)) }

// --- reducer ----------------------------------------------------------------

// Whether two queue snapshots are the same list. Ids are minted once and
// never reused, and a stored item's fields never change after it is added,
// so the id sequence identifies the list without walking the fields.
function sameQueue(a, b) {
  return a === b || (a.length === b.length && a.every((it, i) => it.id === b[i].id))
}

// Pure. Handles the event types the plan lists; everything else (the worker
// results forwarded verbatim) leaves the store alone because the bridge
// follows each of them with a `state` event that carries the consequences.
export function reduce(st, event) {
  switch (event.type) {
    case 'state': {
      // `queue` is lifted out of `server` rather than read from both: the
      // batch list has one home in the store, and the server event is the
      // only thing that fills it (a route's `queue_changed` is followed by
      // this event, which is why nothing reduces that one).
      const { type, counts, queue, ...server } = event
      // It rides along on every state event, progress ticks included, so an
      // unchanged list must come back as the same array or the Queue page
      // re-renders several times a second.
      const items = Array.isArray(queue) ? queue : st.queue
      return {
        ...st,
        server,
        counts: counts ?? st.counts,
        queue: sameQueue(items, st.queue) ? st.queue : items,
      }
    }
    case 'log': {
      const line = { stamp: event.stamp, text: event.text, level: event.level }
      const log = st.log.length >= MAX_LOG ? st.log.slice(st.log.length - MAX_LOG + 1) : st.log.slice()
      log.push(line)
      return { ...st, log }
    }
    case 'error':
      return withToast(st, 'error', event.text)
    case 'needs_input': {
      const { type, ...pending_input } = event
      return { ...st, server: { ...(st.server ?? {}), pending_input } }
    }
    case 'login_scan_progress':
    case 'login_accounts_progress': {
      // The scan reports `logged_in`, the login run reports `ok`; both are
      // the live verdict for one profile and both overrule the stored row
      // until the run's result triggers a refetch.
      const live = event.type === 'login_scan_progress' ? event.logged_in : event.ok
      const name = event.profile_name
      if (!name || typeof live !== 'boolean') return st
      const accounts = st.accounts.map(a => (
        a.linked_profile === name || (event.username && a.username === event.username)
          ? { ...a, live } : a))
      return { ...st, accounts }
    }
    case 'login_scan_result':
    case 'login_accounts_result': {
      // The rows are refetched now (ws.js schedules it); drop the live flags
      // so the server's verdict wins from here on.
      const accounts = st.accounts.some(a => a.live !== undefined)
        ? st.accounts.map(a => a.live === undefined ? a : { ...a, live: undefined })
        : st.accounts
      const next = accounts === st.accounts ? st : { ...st, accounts }
      return event.ok === false ? withToast(next, 'error', event.error || 'Run failed') : next
    }
    default:
      return st
  }
}

// --- actions ----------------------------------------------------------------

let bootstrapping = false

// POST a command route. The server answers 202 and the outcome arrives on
// /ws, so the only thing to report here is a refusal (409 while a run is
// active, 400 for an empty selection) or an unreachable PC.
async function command(path, body) {
  try {
    await api.post(path, body)
    return true
  } catch (e) {
    if (e.status !== 401) pushToast('error', e.error || 'Request failed')
    return false
  }
}

export const actions = {
  setAuth(auth) {
    if (auth === state.auth) return
    if (auth === 'out') ws.close()
    setState({ auth })
  },

  // GET /api/state (+ accounts + log tail 500) then open /ws. A 401 means
  // no session: the login page. Any other failure is the PC being away;
  // try again in a few seconds rather than leaving the spinner forever.
  async bootstrap() {
    if (bootstrapping) return
    bootstrapping = true
    try {
      const st = await api.get('/api/state')
      dispatch({ type: 'state', ...st })
      const [acc, log] = await Promise.all([api.get('/api/accounts'), api.get('/api/log?tail=500')])
      setState({ accounts: acc.rows ?? [], log: log.lines ?? [], auth: 'in' })
      ws.connect()
    } catch (e) {
      if (e.status !== 401) {
        pushToast('error', `PC unreachable: ${e.error || 'no response'}`)
        setTimeout(actions.bootstrap, 3000)
      }
    } finally {
      bootstrapping = false
    }
  },

  // Throws {status, error} on a wrong password (401) or the rate limit
  // (429) so the login page can say which.
  async login(password) {
    await api.post('/api/login', { password })
    await actions.bootstrap()
  },

  async logout() {
    try { await api.post('/api/logout') } catch { /* the cookie is gone either way */ }
    ws.close()
    state = { ...initialState, auth: 'out', page: state.page }
    listeners.forEach(fn => fn())
  },

  async refreshAccounts() {
    let rows
    try { rows = (await api.get('/api/accounts')).rows ?? [] } catch { return }
    // Keep the client-only live verdicts across a refetch: a refresh
    // mid-run must not blank the rows the run already reported.
    const live = new Map(state.accounts.filter(a => a.live !== undefined).map(a => [rowKey(a), a.live]))
    const accounts = live.size ? rows.map(r => live.has(rowKey(r)) ? { ...r, live: live.get(rowKey(r)) } : r) : rows
    const keys = new Set(accounts.map(rowKey))
    const selected = [...state.selected].some(k => !keys.has(k))
      ? new Set([...state.selected].filter(k => keys.has(k))) : state.selected
    setState({ accounts, selected })
  },

  async refreshState() {
    try { dispatch({ type: 'state', ...(await api.get('/api/state')) }) } catch { /* 401 handled by api.js; else the ws banner says it */ }
  },

  setSelected(set) { setState({ selected: new Set(set) }) },
  toggleSelected(key) {
    const selected = new Set(state.selected)
    if (selected.has(key)) selected.delete(key); else selected.add(key)
    setState({ selected })
  },
  clearSelected() { if (state.selected.size) setState({ selected: new Set() }) },

  loginPending() { return command('/api/accounts/login-pending', {}) },
  loginSelected(usernames) { return command('/api/accounts/login', { usernames }) },
  checkLogin(profileNames) { return command('/api/accounts/check-login', { profile_names: profileNames ?? null }) },
  autoSetupAll(profileNames, opts = {}) {
    return command('/api/accounts/auto-setup-all', {
      target_friends: 0, pinterest_query: null, bio: null, connect_friends: true,
      ...opts, profile_names: profileNames,
    })
  },
  acceptPending(profileNames) { return command('/api/accounts/accept-pending', { profile_names: profileNames }) },
  launch(profileName) { return command('/api/profiles/launch', { profile_name: profileName }) },

  async link(username, profileName) {
    const ok = await command('/api/accounts/link', { username, profile_name: profileName })
    if (ok) await actions.refreshAccounts()
    return ok
  },
  async unlink(username) {
    try { await api.del(`/api/accounts/link/${encodeURIComponent(username)}`) }
    catch (e) { if (e.status !== 401) pushToast('error', e.error || 'Unlink failed'); return false }
    await actions.refreshAccounts()
    return true
  },

  // {profile_pic: <image id>|null, cancel: bool}. A 409 means another
  // device answered first; either way the prompt is gone.
  async answerInput({ profile_pic = null, cancel = false } = {}) {
    let ok = true
    try { await api.post('/api/input', { profile_pic, cancel }) }
    catch (e) { ok = false; if (e.status !== 401 && e.status !== 409) pushToast('error', e.error || 'Could not answer the prompt') }
    if (state.server?.pending_input) setState({ server: { ...state.server, pending_input: null } })
    return ok
  },

  stopAll() { return command('/api/stop', {}) },

  // Create and link a Brave profile for every roster row that has none.
  // Long and filesystem-bound on the PC: the answer is 202 and the progress
  // arrives as log lines, so the page watches server.provision_active.
  provisionProfiles() { return command('/api/accounts/provision', {}) },

  // One tap for a pending row: create the Brave profile it lacks, then log
  // that account in. Two existing runs chained on the PC.
  setupAndLogin(usernames) {
    return command('/api/accounts/setup-and-login', { usernames: usernames ?? [] })
  },

  // --- Queue -----------------------------------------------------------
  // The list lives on the PC, so nothing here edits st.queue: every route
  // below is followed by a state event that carries the new list, and a
  // local edit would only disagree with the phone that added the item.

  // One form, one item per profile - the same fan-out QueueTab did when it
  // added a row for every displayed profile.
  queueAdd({ profile_names, action_type, post_url, group_name, comment_text, reaction, text } = {}) {
    return command('/api/queue/add', {
      profile_names: profile_names ?? [],
      action_type: action_type ?? 'group',
      post_url: post_url ?? null,
      group_name: group_name ?? null,
      comment_text: comment_text ?? null,
      reaction: reaction ?? null,
      text: text ?? null,
    })
  },
  // By id, not by index: another device's remove shifts every row under it.
  queueRemove(id) { return command('/api/queue/remove', { id }) },
  queueClear() { return command('/api/queue/clear', {}) },
  queueRun() { return command('/api/queue/run', {}) },
  queueStop() { return command('/api/queue/stop', {}) },
  // Opens a visible Brave window per profile on the PC, which may be a room
  // away - the page says so before the tap.
  queueWatch({ url, minutes, profile_names } = {}) {
    return command('/api/queue/watch', {
      url: url ?? '',
      minutes: minutes ?? null,
      profile_names: profile_names ?? null,
    })
  },
  queueStopWatch() { return command('/api/queue/stop-watch', {}) },

  // --- Groups ----------------------------------------------------------

  // The saved list as the PC last fetched it. A read, not a command: a
  // failure is the connection, which the banner already reports, so it
  // raises no toast of its own.
  async refreshGroups() {
    setState({ groupsLoading: true })
    try {
      setState({ groups: (await api.get('/api/groups')).groups ?? [] })
    } catch { /* 401 shows the login page; anything else the ws banner says */ }
    finally { setState({ groupsLoading: false }) }
  },

  // Exactly one name takes the single-profile fetch and anything else the
  // bulk sweep, but the route decides that - the page has one button either
  // way, as the Tk tab's two were.
  fetchGroups(profileNames) {
    return command('/api/groups/fetch', { profile_names: profileNames ?? null })
  },

  // --- Compose ---------------------------------------------------------

  composeShare({ post_url, group_name, comment_text, reaction } = {}) {
    return command('/api/compose/share', {
      post_url: post_url ?? '',
      group_name: group_name ?? '',
      comment_text: comment_text ?? null,
      reaction: reaction ?? null,
    })
  },

  composeShareTimeline({ post_url, comment_text, reaction } = {}) {
    return command('/api/compose/share-timeline', {
      post_url: post_url ?? '',
      comment_text: comment_text ?? null,
      reaction: reaction ?? null,
    })
  },

  // groups: [{name}] - the worker searches Facebook for each name.
  composeShareGroups({ post_url, groups, comment_text, reaction } = {}) {
    return command('/api/compose/share-groups', {
      post_url: post_url ?? '',
      groups: groups ?? [],
      comment_text: comment_text ?? null,
      reaction: reaction ?? null,
    })
  },

  // groups: [{name, url, profiles}] - rows straight out of st.groups, since
  // the bulk share opens every profile that is a member of each one.
  composeShareBulk({ post_url, groups, comment_text, reaction, profile_names } = {}) {
    return command('/api/compose/share-bulk', {
      post_url: post_url ?? '',
      groups: groups ?? [],
      comment_text: comment_text ?? null,
      reaction: reaction ?? null,
      profile_names: profile_names ?? null,
    })
  },

  composeJoin({ urls, profile_names } = {}) {
    return command('/api/compose/join', {
      urls: urls ?? [],
      profile_names: profile_names ?? null,
    })
  },

  composePostTimeline({ text, image_paths } = {}) {
    return command('/api/compose/post-timeline', {
      text: text ?? '',
      image_paths: image_paths ?? null,
    })
  },

  // Multipart, so it cannot go through api.js. Content-Type is left unset
  // on purpose: the browser writes the multipart boundary into it, and a
  // hand-set header loses that. Throws instead of raising a toast, because
  // only the form knows which of the picked files was refused.
  async uploadImage(file) {
    const form = new FormData()
    form.append('file', file)
    let res
    try {
      res = await fetch('/api/uploads', { method: 'POST', credentials: 'same-origin', body: form })
    } catch {
      throw { status: 0, error: 'PC unreachable' }
    }
    const text = await res.text()
    let data = null
    try { data = text ? JSON.parse(text) : null } catch { data = null }
    if (!res.ok) {
      if (res.status === 401) actions.setAuth('out')
      throw { status: res.status, error: (data && data.error) || res.statusText || `HTTP ${res.status}` }
    }
    return data
  },

  dismissToast(id) {
    if (state.toasts.some(t => t.id === id)) setState({ toasts: state.toasts.filter(t => t.id !== id) })
  },

  navigate(key) {
    if (key === state.page || !PAGES.some(p => p.key === key)) return
    write(LS_PAGE, key)
    setState({ page: key })
  },
}
