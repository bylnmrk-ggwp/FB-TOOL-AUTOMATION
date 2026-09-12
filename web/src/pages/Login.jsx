import { useState } from 'react'
import { actions } from '../store.js'

// One operator, one password (scripts/set_web_password.py). The server
// answers 401 for a wrong password and 429 after five misses in fifteen
// minutes; both are said plainly here instead of a generic "login failed".
export default function Login({ theme, onToggleTheme }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const base = import.meta.env.BASE_URL

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
    }
  }

  return (
    <div className="login">
      <form className="login-card card" onSubmit={submit}>
        <img className="login-logo" src={`${base}logo_${theme}.png`} alt="MCARSPH" draggable={false} />
        <h1 className="card-title">Sign in to AutoShare</h1>
        <label className="field">
          <span>Password</span>
          <input className="input" type="password" name="password" autoComplete="current-password"
                 autoFocus value={password} onChange={e => setPassword(e.target.value)} disabled={busy} />
        </label>
        {error && <div className="login-error" role="alert">{error}</div>}
        <button type="submit" className="btn accent" disabled={busy || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <button type="button" className="btn header-btn login-theme" onClick={onToggleTheme}>
          <span aria-hidden="true">{theme === 'light' ? '☾' : '☀'}</span>
          {theme === 'light' ? 'Dark' : 'Light'}
        </button>
      </form>
    </div>
  )
}
