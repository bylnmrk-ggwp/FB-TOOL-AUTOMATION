# web/ — the AutoShare web app

React + Vite PWA that `server.py` serves from `web/dist`. It is a remote
control for the `DriverManager` on the operator's PC: phones, laptops and
the installed desktop app all open the same page.

    npm ci               # once, or after package.json changes
    npm run build        # -> web/dist (BUILD_WEB.bat does the same)
    npm run dev          # http://localhost:5173, proxies /api and /ws to :8000

For `npm run dev` start the backend with `python server.py --dev` so the
localhost origins are allowed on state-changing requests.

## Layout

| file | role |
|---|---|
| `src/store.js` | the one store: `PAGES`, `initialState`, `useStore`, `actions`, `reduce`, `rowKey` |
| `src/api.js` | `get` / `post` / `del` for `/api`, same-origin cookie, throws `{status, error}`, 401 logs out |
| `src/ws.js` | `/ws` client: events -> `reduce`, backoff 1 s -> 30 s, refetch on every (re)open |
| `src/App.jsx` | shell: Login / spinner / sidebar + header + status bar, theme dip, page slide, phone tab bar |
| `src/components/` | `Sidebar`, `Header`, `StatusBar`, `TabBar` (phones), `Toasts`, `InputPrompt` (image picker) |
| `src/pages/` | `Login`, `Placeholder` (phase-2 sections); Dashboard, Accounts, Log arrive with plan Task F2 |
| `src/theme.css` | palette, spacing, type and motion tokens copied from `src/ui/theme.py` |
| `src/app.css` | shell and component styles, responsive rules, reduced-motion switch |
| `public/` | logos from `src/ui/assets/`, PWA icons generated from `logo_light.png` |

Rules kept from the desktop app: brand red only on the logo and the
active-nav bar, indigo is the single accent, cards are fills not borders,
motion durations come from `theme.py MOTION`, and `prefers-reduced-motion`
turns every tween off.

## Store contract

`store.js` is what the pages code against. `useStore(selector)` reads one
field (`useStore(s => s.counts)`); the selector must return something
referentially stable for an unchanged store. `actions.*` are the only
writers: `bootstrap`, `login`, `logout`, `refreshAccounts`, `refreshState`,
selection (`setSelected`, `toggleSelected`, `clearSelected`), commands
(`loginPending`, `loginSelected`, `checkLogin`, `autoSetupAll`,
`acceptPending`, `launch`, `link`, `unlink`, `answerInput`, `stopAll`),
`dismissToast` and `navigate`. Command actions resolve `true` when the
server accepted (202); a refusal is shown as a toast and resolves `false`.
`reduce(state, event)` is pure and exported for tests.

## Layout below 768 px

The sidebar is replaced by a fixed bottom tab bar, the status bar folds
into a line under the header (activity + progress), stat cards go two per
row, the three dashboard cards stack, and tables scroll inside their card.

## PWA

`vite-plugin-pwa` writes `manifest.webmanifest` and `sw.js`. The service
worker precaches the app shell only; `/api` and `/ws` are never cached.
Icons: `public/icon-192.png`, `icon-512.png`, `apple-touch-icon.png` are the
light logo centred on a white square (Pillow, 80 % width so the maskable
safe zone keeps the wordmark). Regenerate after a logo change:

    python -c "from PIL import Image; L=Image.open('src/ui/assets/logo_light.png').convert('RGBA'); exec(\"for n,s in (('icon-192.png',192),('icon-512.png',512),('apple-touch-icon.png',180)):\\n w=int(s*0.8); h=round(L.height*w/L.width); f=L.resize((w,h),Image.LANCZOS); c=Image.new('RGB',(s,s),'white'); c.paste(f,((s-w)//2,(s-h)//2),f); c.save('web/public/'+n,optimize=True)\")"

On a phone open `https://<host>` (HTTPS is required for the install), log
in, then Share -> Add to Home Screen (iOS) or Install app (Android).

## Proof

`proofs/25_web_build.py` (run by `python verify.py`) runs `npm ci` and
`npm run build` and asserts `dist/index.html`, `dist/manifest.webmanifest`
and `dist/sw.js` exist. It prints `SKIP: node not installed` when npm is
absent.
