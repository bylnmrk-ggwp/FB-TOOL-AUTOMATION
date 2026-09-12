// Stands in for the sections that phase 1 does not ship (Queue, Compose,
// Monitor). The Tk app still does everything, so say where to go.
export default function Placeholder({ page }) {
  return (
    <div className="placeholder">
      <h2 className="card-title">{page.title}</h2>
      <p className="muted mt-sm">Coming in phase 2 — use the desktop app (RUN_APP.bat) for now</p>
    </div>
  )
}
