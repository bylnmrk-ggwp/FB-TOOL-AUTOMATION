import { useEffect, useRef, useState } from 'react'
import { actions } from '../store.js'

// One operator, one password (scripts/set_web_password.py). The server answers
// 401 for a wrong password and 429 after five misses in fifteen minutes; both
// are said plainly here instead of a generic "login failed".
//
// The build sha comes from /api/health, the one public route: it tells the
// operator which version the tunnel is serving before they are even signed in,
// which is the question a stale PWA cache usually raises.
export default function Login({ theme, onToggleTheme }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [reveal, setReveal] = useState(false)
  const [version, setVersion] = useState('')
  const input = useRef(null)
  const base = import.meta.env.BASE_URL

  useEffect(() => {
    let live = true
    fetch('/api/health', { credentials: 'same-origin' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (live && d && d.version) setVersion(d.version) })
      .catch(() => { /* the error line below already covers an unreachable PC */ })
    return () => { live = false }
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    if (!password || busy) return
    setBusy(true)
    setError('')
    try {
      await actions.login(password)
    } catch (err) {
      if (err.status === 401) setError('Wrong password.')
      else if (err.status === 429) setError('Too many attempts. Wait 15 minutes and try again.')
      else setError(err.error || 'PC unreachable.')
      setBusy(false)
      setPassword('')
      input.current?.focus()
    }
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <span className="login-bar" aria-hidden="true" />

        <div className="login-head">
          <img className="login-logo" src={`${base}logo_${theme}.png`} alt="MCARSPH" draggable={false} />
          <h1 className="login-title">AutoShare</h1>
          <p className="login-sub">Operator sign-in</p>
        </div>

        <label className="field login-field">
          <span>Password</span>
          <span className="login-input-wrap">
            <input ref={input} className="input" type={reveal ? 'text' : 'password'}
                   name="password" autoComplete="current-password" autoFocus
                   value={password} onChange={e => setPassword(e.target.value)} disabled={busy} />
            <button type="button" className="login-reveal" tabIndex={-1}
                    aria-label={reveal ? 'Hide password' : 'Show password'}
                    onClick={() => setReveal(r => !r)} disabled={busy}>
              {reveal ? 'Hide' : 'Show'}
            </button>
          </span>
        </label>

        {error && <div className="login-alert" role="alert"><span aria-hidden="true">✗</span>{error}</div>}

        <button type="submit" className="btn accent login-submit" disabled={busy || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <div className="login-foot">
          <span className="muted small">
            Controls the bot on this PC{version ? ` · build ${version}` : ''}
          </span>
          <button type="button" className="login-theme" onClick={onToggleTheme}>
            <span aria-hidden="true">{theme === 'light' ? '☾' : '☀'}</span>
            {theme === 'light' ? 'Dark' : 'Light'}
          </button>
        </div>
      </form>
    </div>
  )
}
