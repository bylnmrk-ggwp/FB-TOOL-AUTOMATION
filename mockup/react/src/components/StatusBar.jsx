// Phase A status bar: activity text on the left, a progress bar while a run
// is active, counts on the right. The progress value tweens (200 ms).
export default function StatusBar({ activity, run, right }) {
  const pct = run.total ? Math.round((run.done / run.total) * 100) : 0
  return (
    <footer className="statusbar" role="status" aria-live="polite">
      <span className="sb-left">{activity}</span>
      {run.active && (
        <>
          <span className="progress sb-progress" aria-hidden="true"><span style={{ width: pct + '%' }} /></span>
          <span>{run.done}/{run.total}</span>
        </>
      )}
      <span className="spacer" />
      <span className="sb-right">{right}</span>
    </footer>
  )
}
