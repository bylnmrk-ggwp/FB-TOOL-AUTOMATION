import { useMemo } from 'react'
import { detectGlyphFont, Glyph } from './Sidebar.jsx'

// The phone replacement for the sidebar: six glyphs along the bottom, the
// active one marked with the same brand-red bar, on top instead of at the
// left. Only rendered below 768 px (App.jsx) and only shown there (app.css).
export default function TabBar({ pages, active, onSelect }) {
  const glyphFont = useMemo(detectGlyphFont, [])
  return (
    <nav className="tabbar" aria-label="Sections">
      {pages.map(p => (
        <button key={p.key} type="button"
                className={'tab' + (p.key === active ? ' active' : '')}
                aria-current={p.key === active ? 'page' : undefined}
                aria-label={p.title}
                onClick={() => onSelect(p.key)}>
          <Glyph font={glyphFont} fluent={p.glyph} fallback={p.fallback} />
          <span className="tab-label">{p.title}</span>
        </button>
      ))}
    </nav>
  )
}
