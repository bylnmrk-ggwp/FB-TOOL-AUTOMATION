# Remote access: the control panel on Vercel, the API through Tailscale Funnel

Date: 2026-10-07
Status: approved in conversation, awaiting spec review

## Why

The control panel at `https://fbtool-phi.vercel.app` is a stale build of the
previous Python system. Its bundle asks for `/api/state`, which nothing
serves, so the page loops on a 404 and shows "PC unreachable". The Vercel
project is linked to this repository's `main` branch through the GitHub
integration; every push builds, and every build has failed since the
TypeScript rewrite because the project still points at the old `web/`
directory.

The rewrite deliberately dropped remote access (README, "Not ported from the
old system"). The operator wants it back: the Vercel URL must open the new
control panel from any device, with a password, and drive the PC.

## Decisions already made

| Question | Decision |
| --- | --- |
| Where the page is served | Vercel, from `apps/web` on `main` |
| How the PC's API becomes reachable | Tailscale Funnel on this PC, `https://<pc>.<tailnet>.ts.net` |
| Who may open the panel | Anyone with the link and the password |
| Login model | One shared password, stateless signed token, like the old `auth.py` |
| Not chosen | Cloudflare Tunnel (needs a domain, none owned), ngrok free (1 GB/month), Vercel rewrites for `/api` (cannot carry WebSocket), serving only from the Funnel host (Vercel URL must keep working) |

## Architecture

```
phone / laptop                 Vercel (static)            this PC
┌──────────────┐  GET /        ┌──────────────┐           ┌─────────────────────────────┐
│ browser      │ ────────────▶ │ apps/web     │           │ tailscaled (Funnel, :443)    │
│              │               │ dist         │           │   └─▶ 127.0.0.1:3001 Fastify │
│              │  /api/v1/*, /ws  (Bearer / ?token=)       │        ├─ auth guard         │
│              │ ─────────────────────────────────────────▶│        ├─ /api/v1/auth/*     │
└──────────────┘               └──────────────┘           │        └─ existing routes    │
                                                          └─────────────────────────────┘
```

The page is static. Its bundle carries the Funnel hostname as the API base,
so every fetch and the one WebSocket go straight to the PC. The API keeps
binding to `127.0.0.1`; Funnel terminates HTTPS and forwards to it. Because
the API already serves `apps/web/dist` at `/`, the Funnel hostname alone also
opens the whole panel; Vercel is a second front door, not a dependency.

## Part 1: server login

### Configuration (`apps/server/src/config/env.ts`)

| Variable | Meaning |
| --- | --- |
| `AUTH_PASSWORD` | Optional. When set, every API call needs a token. When unset, the API is open, as today. |
| `AUTH_SECRET` | Optional. Signs tokens. When unset, a random secret is generated at start, so a restart logs every device out. |

`AppConfig` gains `auth: { password: string | null; secret: string }`, and
`tests/helpers/server.ts` sets `auth: { password: null, secret: 'test-secret' }`
in `testConfig` with a `createTestServer({ auth })` option to override it. At
start the server logs a warning when `AUTH_PASSWORD` is unset ("API has no
login; keep it on 127.0.0.1") and another when `AUTH_SECRET` is unset
("tokens will not survive a restart").

### Module `apps/server/src/http/auth/`

- `tokens.ts`: `issueToken(secret, now)` returns `v1.<issuedAtMs>.<base64url HMAC-SHA256>`;
  `verifyToken(secret, token, now)` returns `true` only when the version is
  `v1`, the signature matches under `timingSafeEqual`, and the token is younger
  than 30 days. Node `crypto` only, no new dependency.
- `rate-limit.ts`: `LoginRateLimiter` with `recordFailure()`, `reset()` and
  `isLimited()`. Five failures inside a sliding 15-minute window block further
  attempts until the oldest failure ages out. One global counter: there is one
  operator, and a global counter cannot be fooled by forged forwarding headers.
- `guard.ts`: `registerAuthGuard(app, config)` adds an `onRequest` hook. When
  `config.auth.password` is `null` the hook is not registered at all. Otherwise
  the hook lets through, in this order: `OPTIONS` requests, any path that does
  not start with `/api/` or `/ws` (the static panel), `/api/v1/health`, and
  `/api/v1/auth/*`. For `/ws` it reads `token` from the query string; for
  everything else it reads `Authorization: Bearer <token>`. A missing or bad
  token answers `401 AUTH_REQUIRED` before any route runs, which for `/ws`
  means the upgrade never happens.

### Routes (`apps/server/src/http/routes/auth.routes.ts`, `controllers/AuthController.ts`)

| Route | Behaviour |
| --- | --- |
| `GET /api/v1/auth/session` | Public. `{ authRequired: boolean, authenticated: boolean }`. `authenticated` reflects the bearer token on this request, so the panel can validate a stored token without a second round trip. |
| `POST /api/v1/auth/login` `{ password }` | When login is off: `409 CONFLICT` "login is not configured". When rate-limited: `429 AUTH_RATE_LIMITED`. Wrong password (timing-safe compare): records a failure, `401 AUTH_INVALID`. Right password: resets the limiter, `{ token, expiresAt }`. |

No logout route: tokens are stateless. Changing `AUTH_SECRET` invalidates
every token at once.

### Shared error codes (`packages/shared/src/errors/codes.ts`)

`AUTH_REQUIRED` (401), `AUTH_INVALID` (401), `AUTH_RATE_LIMITED` (429), raised
through `AppError` so the existing error handler shapes them.

### CORS

No code change. `.env` lists the Vercel origin in `CORS_ORIGIN`. Bearer tokens
need no cookies, so `credentials` stays as it is.

## Part 2: web login

### Token store (`apps/web/src/lib/auth.ts`)

`getToken()`, `setToken()`, `clearToken()` over `localStorage` key
`fb.auth.token`, `authHeaders()` returning `{ authorization: 'Bearer …' }` or
`{}`, and `onUnauthorized(listener)` so the gate can react to a 401 raised
anywhere.

### Where the header is added

The frontend performs network I/O in four places, and all four carry the
token: `api/client.ts` (`apiRequest`), the multipart upload in
`api/system.ts`, the screenshot fetch in
`features/monitoring/components/BrowserGrid.tsx`, and the WebSocket in
`features/automation/useLiveEvents.ts` (as `?token=` on the URL). `apiRequest`
also clears the token and fires `onUnauthorized` when a response is 401 with
`AUTH_REQUIRED` or `AUTH_INVALID`.

### Session and gate

- `api/auth.ts`: `getSession()`, `login(password)`.
- `features/auth/AuthGate.tsx`, mounted in `App.tsx` around the router: on
  mount calls `getSession()`. While loading, a blank screen with the app
  background. When `authRequired` is false, or `authenticated` is true, it
  renders the router. Otherwise it renders `pages/Login/LoginPage.tsx`. It also
  subscribes to `onUnauthorized` and returns to the login page.
- `LoginPage`: one password field, a submit button, the server's error
  message under the field (wrong password, rate limited, unreachable). On
  success it stores the token and the gate re-renders the app.
- Settings page: a "Sign out" button that clears the token and reloads; shown
  only when `authRequired` is true.

### Build-time API base (`apps/web/vite.config.ts`, `lib/env.ts`)

A new build-only variable `VITE_PUBLIC_API_URL` replaces the hard-coded empty
`define`. When it is unset the bundle stays same-origin, exactly as today,
which is what the API's own static serving and the local build rely on. The
dev proxy keeps using `VITE_API_URL`. `WEB_CONFIG.apiBaseUrl` reads the new
variable; `useLiveEvents.socketUrl()` already derives the socket host from it.

## Part 3: Vercel

`vercel.json` at the repository root:

```json
{
  "installCommand": "pnpm install --frozen-lockfile",
  "buildCommand": "pnpm build:packages && pnpm --filter @fb/web build",
  "outputDirectory": "apps/web/dist",
  "framework": null,
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

Vercel detects pnpm from `pnpm-lock.yaml` and honours the `packageManager`
field. `build:packages` runs `tsc` for the workspace packages the web app
imports (`@fb/shared`); nothing touches `node:sqlite` or Playwright at build
time.

Dashboard settings, done once by the operator or through the operator's
browser: Root Directory cleared (it currently says `web`), Node.js 22,
Production environment variable
`VITE_PUBLIC_API_URL=https://<pc>.<tailnet>.ts.net`. Preview deployments are
out of scope; they build but point at no API.

## Part 4: Tailscale on the PC

1. `winget install --id tailscale.tailscale -e`
2. `tailscale up` — the operator signs in in the browser.
3. `tailscale funnel --bg 3001` — the first run prints an admin-console link
   to enable Funnel and HTTPS certificates for the tailnet. The setting
   persists in Tailscale's state and comes back after a reboot.
4. `.env` on the PC gains `AUTH_PASSWORD`, `AUTH_SECRET` (generated with
   `openssl rand -hex 32` or Node), and `https://fbtool-phi.vercel.app` in
   `CORS_ORIGIN`.
5. The server runs as the `admin` user: `pnpm dev` for now, or a service that
   runs under that account later. Never as LocalSystem (see the 2026-10-06
   profile loss).

README: the "Web password authentication for remote access" bullet under "Not
ported from the old system" is removed and a "Remote access" section describes
the variables, the Funnel command and the Vercel settings.

## Part 5: tests

- Unit (`tests/unit/auth-tokens.test.ts`, `tests/unit/login-rate-limit.test.ts`):
  a token verifies under its secret, fails under another, fails when tampered,
  fails after 30 days; the limiter blocks on the fifth failure, frees after the
  window, resets on success.
- Integration (`tests/integration/auth-api.test.ts`), using `createTestServer`
  with an `AUTH_PASSWORD` override: without a token `GET /api/v1/accounts` is
  401 `AUTH_REQUIRED` while `GET /api/v1/health` and `GET /api/v1/auth/session`
  are 200; a wrong password is 401 `AUTH_INVALID`; the sixth wrong password is
  429; the right password returns a token that makes `GET /api/v1/accounts`
  200; a WebSocket upgrade to `/ws` without `token` is refused and with a
  valid token receives `connection.ready`. For the socket test the server
  listens on an ephemeral port and the test uses Node 22's built-in
  `WebSocket` client, so no `ws` dependency is added at the root.
- Every existing test keeps running with login off, because `createTestServer`
  sets no password unless asked.
- Web: `pnpm typecheck` and `pnpm lint`. Manual acceptance on a phone over
  mobile data: open the Vercel URL, log in, see the dashboard update live,
  see the Monitor grid load screenshots, sign out, confirm the login page
  returns.

## Out of scope

Per-user accounts, password change from the UI, token revocation lists,
preview deployments on Vercel, running the API as a Windows service under the
operator's account (separate change).
