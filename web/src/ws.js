// The /ws client. Server to client only: every event is folded into the
// store, and the few that mean "the rows changed on the PC" trigger a
// refetch here rather than inside the pure reducer.
import { dispatch, actions, setState } from './store.js'

const MIN_BACKOFF_MS = 1000
const MAX_BACKOFF_MS = 30000
const CLOSE_UNAUTHORIZED = 4401   // the server's close code for a missing or stale session

let socket = null
let timer = null
let backoff = MIN_BACKOFF_MS
let wanted = false                // false after close(): a deliberate logout must not reconnect

export function connect() {
  wanted = true
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return
  open()
}

export function close() {
  wanted = false
  clearTimeout(timer)
  timer = null
  const s = socket
  socket = null
  if (s) s.close()
}

function open() {
  clearTimeout(timer)
  timer = null
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const s = new WebSocket(`${proto}//${location.host}/ws`)
  socket = s

  s.onopen = () => {
    backoff = MIN_BACKOFF_MS
    setState({ connected: true })
    // A phone that slept for an hour catches up with one fetch each
    // instead of replaying every event it missed.
    actions.refreshState()
    actions.refreshAccounts()
  }

  s.onmessage = (m) => {
    let event
    try { event = JSON.parse(m.data) } catch { return }
    if (!event || typeof event.type !== 'string') return
    handle(event)
  }

  s.onclose = (e) => {
    if (socket !== s) return          // superseded by a newer socket or close()
    socket = null
    setState({ connected: false })
    if (e.code === CLOSE_UNAUTHORIZED) { actions.setAuth('out'); return }
    if (wanted) schedule()
  }

  s.onerror = () => { /* onclose follows and does the work */ }
}

// Exponential backoff 1 s -> 30 s. A dead PC is polled gently; a blip
// reconnects within a second.
function schedule() {
  clearTimeout(timer)
  timer = setTimeout(open, backoff)
  backoff = Math.min(backoff * 2, MAX_BACKOFF_MS)
}

function handle(event) {
  dispatch(event)
  switch (event.type) {
    case 'accounts_changed':        // sheet sync applied on the PC
    case 'login_scan_result':
    case 'login_accounts_result':
      actions.refreshAccounts()
      break
    // A groups fetch rewrites profile_groups on the PC; the event itself
    // carries no rows, so the list is re-read rather than patched.
    case 'fetch_groups_result':
    case 'fetch_groups_bulk_result':
      actions.refreshGroups()
      break
    // `queue_changed` needs nothing here: every queue route pushes a state
    // event straight after it, and that event carries the whole list.
    default:
      break
  }
}

// Phones drop the socket while the app is in the background; reconnect the
// moment it comes back rather than waiting out the current backoff.
if (typeof document !== 'undefined') {
  const wake = () => {
    if (wanted && !socket && !document.hidden) { backoff = MIN_BACKOFF_MS; open() }
  }
  document.addEventListener('visibilitychange', wake)
  window.addEventListener('online', wake)
}
