# Admin shell mockup

Throwaway browser preview of the new admin-shell layout described in
`docs/superpowers/specs/2026-09-12-admin-shell-design.md`. It shares no code
with the Tkinter app; colours, spacing, type sizes and motion durations are
copied from `src/ui/theme.py` so what you see here is what the app will do.

    npm install
    npm run dev        # http://localhost:5173

Everything is fake data (`src/data.js`). The Dashboard button and Queue
"Start Queue" run a pretend job so the progress, count-up and status bar move.
Theme and sidebar state persist in localStorage; `?page=accounts&theme=dark&sidebar=1`
opens a given page directly.
