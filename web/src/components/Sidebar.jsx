import { useEffect, useMemo, useState } from 'react'

const NAV_H = 40, NAV_GAP = 2   // px; must match .nav-item height and .nav gap in app.css

// The Tk sidebar uses Segoe Fluent Icons (Windows 11) or Segoe MDL2 Assets
// (Windows 10) and falls back to plain Unicode. A browser cannot ask whether
// a local face exists, but it can measure: a private-use glyph is wider in
// the icon face than in the fallback face. Phones never have the face and
// get the Unicode fallback, which is why PAGES carries both.
export function detectGlyphFont() {
  try {
    const ctx = document.createElement('canvas').getContext('2d')
    const probe = '\uE80F\uE716\uE8FD\uE7C3'
    const width = (family) => { ctx.font = `16px ${family}`; return ctx.measureText(probe).width }
    const base = width('monospace')
    for (const face of ['"Segoe Fluent Icons"', '"Segoe MDL2 Assets"']) {
      if (width(`${face}, monospace`) !== base) return face
    }
  } catch { /* no canvas: use the fallback glyphs */ }
  return null
}

export function Glyph({ font, fluent, fallback }) {
  return font
    ? <span className="glyph fluent" style={{ fontFamily: font }} aria-hidden="true">{fluent}</span>
    : <span className="glyph" aria-hidden="true">{fallback}</span>
}

export default function Sidebar({ pages, active, onSelect, collapsed, onToggle, theme }) {
  const glyphFont = useMemo(detectGlyphFont, [])
  const [imgFailed, setImgFailed] = useState({ light: false, dark: false })
  const [tip, setTip] = useState(null)
  const activeIndex = Math.max(0, pages.findIndex(p => p.key === active))
  const base = import.meta.env.BASE_URL

  useEffect(() => { if (!collapsed) setTip(null) }, [collapsed])

  const showTip = (e, label) => {
    if (!collapsed) return
    const r = e.currentTarget.getBoundingClientRect()
    setTip({ label, top: r.top + r.height / 2 })
  }
  const hideTip = () => setTip(null)

  return (
    <aside className={'sidebar' + (collapsed ? ' collapsed' : '')} aria-label="Sections">
      <div className="logo">
        {/* Collapsed shows the square monogram, not the full lockup: cropping
            the wide logo into a 40 px rail sliced the wheel mid-shape and read
            as a broken image. */}
        {collapsed
          ? <img className="mark" src={`${base}logo_mark.png`} alt="MCARSPH" draggable={false} />
          : ['light', 'dark'].map(mode => imgFailed[mode] ? null : (
            <img key={mode} src={`${base}logo_${mode}.png`} alt="MCARSPH" hidden={theme !== mode}
                 draggable={false} onError={() => setImgFailed(f => ({ ...f, [mode]: true }))} />
          ))}
        {!collapsed && imgFailed[theme] && <div className="wordmark"><span>MCARS</span><span className="brand">PH.</span></div>}
      </div>

      <nav className="nav">
        <span className="nav-bar" style={{ transform: `translateY(${activeIndex * (NAV_H + NAV_GAP)}px)` }} aria-hidden="true" />
        {pages.map(p => (
          <button key={p.key} type="button"
                  className={'nav-item' + (p.key === active ? ' active' : '')}
                  aria-current={p.key === active ? 'page' : undefined}
                  aria-label={p.title}
                  onClick={() => onSelect(p.key)}
                  onMouseEnter={e => showTip(e, p.title)} onMouseLeave={hideTip}
                  onFocus={e => showTip(e, p.title)} onBlur={hideTip}>
            <Glyph font={glyphFont} fluent={p.glyph} fallback={p.fallback} />
            <span className="label">{p.title}</span>
          </button>
        ))}
      </nav>

      <button type="button" className="nav-item collapse" onClick={onToggle}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              onMouseEnter={e => showTip(e, 'Expand')} onMouseLeave={hideTip}
              onFocus={e => showTip(e, 'Expand')} onBlur={hideTip}>
        <Glyph font={glyphFont} fluent={collapsed ? '\uE76C' : '\uE76B'} fallback={collapsed ? '\u203A' : '\u2039'} />
        <span className="label">Collapse</span>
      </button>

      {tip && collapsed && <div className="side-tip" style={{ top: tip.top }} role="tooltip">{tip.label}</div>}
    </aside>
  )
}
