export default function Header({ title, chip, theme, onToggleTheme, onLogout }) {
  const toDark = theme === 'light'
  return (
    <header className="header">
      <h1 className="page-title">{title}</h1>
      {chip && <span className="chip">{chip}</span>}
      <span className="spacer" />
      <button type="button" className="btn header-btn" onClick={onToggleTheme}
              aria-label={toDark ? 'Switch to dark theme' : 'Switch to light theme'}>
        <span aria-hidden="true">{toDark ? '\u263e' : '\u2600'}</span>
        {toDark ? 'Dark' : 'Light'}
      </button>
      <button type="button" className="btn header-btn" onClick={onLogout}>
        <span aria-hidden="true">{'\u238b'}</span>
        Log Out
      </button>
    </header>
  )
}
