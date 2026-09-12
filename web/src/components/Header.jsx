export default function Header({ title, chip, theme, onToggleTheme, onLogout }) {
  const toDark = theme === 'light'
  return (
    <header className="header">
      <h1 className="page-title">{title}</h1>
      {chip && <span className="chip">{chip}</span>}
      <span className="spacer" />
      <button type="button" className="btn header-btn" onClick={onToggleTheme}
              aria-label={toDark ? 'Switch to dark theme' : 'Switch to light theme'}>
        <span aria-hidden="true">{toDark ? '☾' : '☀'}</span>
        <span className="btn-text">{toDark ? 'Dark' : 'Light'}</span>
      </button>
      <button type="button" className="btn header-btn" onClick={onLogout} aria-label="Log out">
        <span aria-hidden="true">{'⎋'}</span>
        <span className="btn-text">Log Out</span>
      </button>
    </header>
  )
}
