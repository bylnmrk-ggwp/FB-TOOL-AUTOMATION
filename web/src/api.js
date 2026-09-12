// Thin fetch wrapper for /api. Same-origin cookies carry the session; every
// failure is thrown as {status, error} so callers can switch on the status
// (401 wrong password, 409 run active, 429 rate limited, 0 unreachable).
import { actions } from './store.js'

// FastAPI's validation errors come as {"detail": [...]}; the app's own
// errors as {"error": "..."}. One readable string out of either.
function messageOf(data, res) {
  if (data && typeof data.error === 'string') return data.error
  const d = data && data.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d) && d.length) return d.map(x => x.msg || JSON.stringify(x)).join('; ')
  return res.statusText || `HTTP ${res.status}`
}

async function request(method, path, body) {
  const init = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } }
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(path, init)
  } catch {
    throw { status: 0, error: 'PC unreachable' }
  }
  if (res.status === 204) return null
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = null }
  if (!res.ok) {
    // No session (or an expired one): show the login page. A wrong password
    // on /api/login is also a 401, but the app is already logged out then.
    if (res.status === 401) actions.setAuth('out')
    throw { status: res.status, error: messageOf(data, res) }
  }
  return data
}

export const get = (path) => request('GET', path)
export const post = (path, body = {}) => request('POST', path, body)
export const del = (path) => request('DELETE', path)
