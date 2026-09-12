import { useEffect, useRef, useState } from 'react'

const COUNT_MS = 300   // theme.py MOTION["count"]; theme.css --m-count
const easeOutCubic = t => 1 - Math.pow(1 - t, 3)
const reduced = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Count-up from the value last shown to the new one over 300 ms on
// requestAnimationFrame, like effects.count_up in the Tk app. Reduced
// motion jumps straight to the value. A non-number (counts not loaded
// yet) shows as 0 without animating.
export function useCountUp(value) {
  const target = Number.isFinite(value) ? value : 0
  const [shown, setShown] = useState(target)
  const cur = useRef(target)
  useEffect(() => {
    const a = cur.current, b = target
    if (a === b) return undefined
    if (reduced()) { cur.current = b; setShown(b); return undefined }
    const start = performance.now()
    let raf = 0
    const step = (now) => {
      const t = Math.min(1, (now - start) / COUNT_MS)
      cur.current = Math.round(a + (b - a) * easeOutCubic(t))
      setShown(cur.current)
      if (t < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target])
  return shown
}

export default function StatCard({ title, value, hint }) {
  const n = useCountUp(value)
  return (
    <div className="card stat">
      <div className="muted">{title}</div>
      <div className="stat-value">{n}</div>
      {hint && <div className="muted small">{hint}</div>}
    </div>
  )
}
