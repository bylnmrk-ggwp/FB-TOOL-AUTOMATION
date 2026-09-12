import { useEffect } from 'react'
import { useStore, actions } from '../store.js'

const TOAST_MS = 6000

// Bottom-right on desktop, top on phones (app.css). Each toast dismisses
// itself after 6 s or on tap; the timer lives here, not in the store, so
// the reducer stays pure.
export default function Toasts() {
  const toasts = useStore(s => s.toasts)
  if (toasts.length === 0) return null
  return (
    <div className="toasts">
      {toasts.map(t => <Toast key={t.id} toast={t} />)}
    </div>
  )
}

function Toast({ toast }) {
  useEffect(() => {
    const id = setTimeout(() => actions.dismissToast(toast.id), TOAST_MS)
    return () => clearTimeout(id)
  }, [toast.id])
  return (
    <div className={'toast ' + toast.level} role="status" onClick={() => actions.dismissToast(toast.id)}>
      {toast.text}
    </div>
  )
}
