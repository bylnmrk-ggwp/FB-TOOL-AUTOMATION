/** Scripts that run inside a live-video page. */
export const watchScripts = {
  /** Where the player is, in seconds; null without a player. */
  currentTime: `() => { const v = document.querySelector('video'); return v ? v.currentTime : null; }`,

  /**
   * Pull the player to the live edge, unmute-proof it and press play. Returns
   * false when there is no player on the page at all.
   */
  kick: `() => {
    const v = document.querySelector('video');
    if (!v) return false;
    try {
      if (v.seekable.length) {
        const end = v.seekable.end(v.seekable.length - 1);
        if (end - v.currentTime > 1) v.currentTime = Math.max(0, end - 1);
      }
    } catch (e) {}
    v.muted = true;
    v.play().catch(() => {});
    return true;
  }`,

  /** One health sample: is there a player, is it paused or ended, where is it. */
  probe: `() => {
    const v = document.querySelector('video');
    if (!v) return { video: false, t: 0, paused: true, ended: true };
    let resumed = false;
    if (v.paused || v.ended) { v.muted = true; v.play().catch(() => {}); resumed = true; }
    return { video: true, t: v.currentTime || 0, paused: v.paused, ended: v.ended, resumed };
  }`,

  /** Facebook's own viewer figure, off the player's aria-label. */
  viewers: `() => {
    for (const el of document.querySelectorAll('[aria-label]')) {
      const a = el.getAttribute('aria-label') || '';
      if (!/currently watching/i.test(a)) continue;
      const m = a.match(/([\\d.,]+\\s*[KMB]?)\\s+(?:people|person)/i);
      if (m) return m[1].trim();
    }
    return null;
  }`,

  /** Words the page shows once a broadcast is over. */
  endedTexts: [
    'this live video has ended',
    'the live video has ended',
    'video is no longer available',
  ],
} as const;
