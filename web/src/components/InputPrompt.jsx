import { useState } from 'react'
import { actions } from '../store.js'

// The web form of ImagePickerDialog: the worker paused an auto-setup and
// wants a profile picture chosen from the Pinterest images it downloaded.
// "Use this" answers with the image id, "Skip" continues without a picture
// (profile_pic null, cancel false, exactly what Apply-with-None sent in Tk).
// The first device to answer wins; the server clears the prompt for all.
export default function InputPrompt({ prompt }) {
  const [busy, setBusy] = useState(false)
  const images = prompt.images ?? []

  const answer = async (profile_pic) => {
    setBusy(true)
    try { await actions.answerInput({ profile_pic, cancel: false }) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="input-prompt-title">
      <div className="modal card">
        <h2 id="input-prompt-title" className="card-title">Profile picture for {prompt.profile_name}</h2>
        <p className="muted small mt-xs">
          {prompt.needs_pic
            ? 'Pick one of the downloaded images, or skip to continue without a picture.'
            : 'This profile already has a picture. Skip to continue, or pick one to replace it.'}
        </p>
        {images.length === 0
          ? <p className="muted mt-md">No images were downloaded.</p>
          : (
            <div className="image-grid mt-md">
              {images.map((im, i) => (
                <figure key={im.id} className="image-cell">
                  <img src={im.url} alt={`Image ${i + 1}`} loading="lazy" />
                  <button type="button" className="btn sm accent" disabled={busy} onClick={() => answer(im.id)}>
                    Use this
                  </button>
                </figure>
              ))}
            </div>
          )}
        <div className="btn-row mt-md">
          <span className="muted small">The auto-setup on the PC is waiting for this answer.</span>
          <span className="spacer" />
          <button type="button" className="btn" disabled={busy} onClick={() => answer(null)}>Skip</button>
        </div>
      </div>
    </div>
  )
}
