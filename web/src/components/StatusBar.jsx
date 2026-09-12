// Activity text on the left, a progress bar while a run is active, counts
// on the right. `run` is AppState.run: null, or {kind, current, total,
// message, profile_name}. The progress value tweens (200 ms, app.css).
// `fold` is the phone variant that sits under the header: activity and
// progress only, the counts are on the Dashboard anyway.
export default function StatusBar({ activity, run, right, fold = false }) {
  const pct = run && run.total ? Math.round((run.current / run.total) * 100) : 0
  return (
    <footer className={'statusbar' + (fold ? ' fold' : '')} role="status" aria-live="polite">
      <span className="sb-left">{activity}</span>
      {run && (
        <>
          <span className="progress sb-progress" aria-hidden="true"><span style={{ width: pct + '%' }} /></span>
          <span>{run.current}/{run.total}</span>
        </>
      )}
      <span className="spacer" />
      {!fold && <span className="sb-right">{right}</span>}
    </footer>
  )
}
