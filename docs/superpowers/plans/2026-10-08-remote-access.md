# Remote Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The control panel at `https://fbtool-phi.vercel.app` opens the new `apps/web` build, asks for a password, and drives the API on this PC through a Tailscale Funnel hostname.

**Architecture:** The server gains an optional password login that issues stateless HMAC tokens; a Fastify `onRequest` guard demands the token on every `/api/v1/*` call except health and auth, and on the `/ws` upgrade. The web app stores the token, sends it on its four network paths, and shows a login page until it has one. Vercel builds `apps/web` with the Funnel hostname baked in; the API stays bound to `127.0.0.1` behind `tailscale funnel`.

**Tech Stack:** Fastify 5, zod 3, Node 22 `crypto` and global `WebSocket`, React 18 + TanStack Query + react-router 6, Vite 6, Vitest 2, pnpm 9 workspaces, Vercel static hosting, Tailscale Funnel.

**Spec:** `docs/superpowers/specs/2026-10-07-remote-access-design.md`

## Global Constraints

- Node `>=22.5.0` (root `package.json` engines); tests may rely on the global `WebSocket` client.
- No new runtime dependency on the server; tokens use `node:crypto` only.
- No new root devDependency; the socket test uses Node's built-in `WebSocket`.
- TypeScript is strict with `noUncheckedIndexedAccess`, `noUnusedLocals`, `noUnusedParameters`, `verbatimModuleSyntax`; `exactOptionalPropertyTypes` is off.
- `import.meta.env` keys are read with bracket access (`import.meta.env['NAME']`), matching `apps/web/src/lib/env.ts`.
- Server-side unit and integration tests import the **built** output (`@fb/server/app`, `apps/server/dist/...`). Run `pnpm build:packages && pnpm --filter @fb/server build` before `vitest`.
- Commit messages follow the repository style: `type: a short sentence describing the behaviour`, ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never push. Commit locally only.
- The API keeps `HOST=127.0.0.1`. Nothing in this plan binds to another interface.
- Token lifetime is 30 days. Login limit is 5 failures per 15 minutes, one global counter.
- Error codes added: `AUTH_REQUIRED` (401), `AUTH_INVALID` (401), `AUTH_RATE_LIMITED` (429).

## Review Focus

1. `Authorization` header present but malformed (`Basic …`, `Bearer` with nothing after it, `bearer x` lower-case) must answer 401 `AUTH_REQUIRED`, never 500. Test in Task 5.
2. A token with a non-numeric or future `issuedAt`, or with an extra segment, must verify `false` and never throw. Test in Task 3.
3. A login body with an empty or missing `password` must be 400 `VALIDATION_ERROR` and must not count as a failed attempt. Test in Task 5.
4. `VITE_PUBLIC_API_URL` given with a trailing slash must not produce `//api/v1` URLs. Test in Task 7.
5. Static files and the page itself (`GET /`, `GET /assets/app.js`) must never be gated, so a phone can load the panel before it has a token. Test in Task 5.

## File Structure

| Path | Responsibility |
| --- | --- |
| `packages/shared/src/errors/codes.ts` | Three new error codes. |
| `packages/shared/src/errors/auth-errors.ts` (new) | `AuthRequiredError`, `AuthInvalidError`, `AuthRateLimitedError`. |
| `packages/shared/src/schemas/auth.ts` (new) | `LoginRequestSchema`, `LoginResponseSchema`, `AuthSessionSchema` and their types. |
| `apps/server/src/config/env.ts` | `AUTH_PASSWORD`, `AUTH_SECRET` → `AppConfig.auth`. |
| `apps/server/src/main.ts` | Startup warnings about missing password or secret. |
| `apps/server/src/http/auth/tokens.ts` (new) | Issue and verify stateless tokens. |
| `apps/server/src/http/auth/rate-limit.ts` (new) | `LoginRateLimiter`. |
| `apps/server/src/http/auth/guard.ts` (new) | `registerAuthGuard`. |
| `apps/server/src/http/auth/password.ts` (new) | `passwordMatches` timing-safe compare. |
| `apps/server/src/http/controllers/AuthController.ts` (new) | `session`, `login` handlers. |
| `apps/server/src/http/routes/auth.routes.ts` (new) | Mounts `/auth/session`, `/auth/login`. |
| `apps/server/src/http/routes/index.ts` | Registers the auth routes. |
| `apps/server/src/app.ts` | Calls `registerAuthGuard` before the WebSocket and routes. |
| `tests/helpers/server.ts` | `auth` in `testConfig`; `createTestServer({ auth })`. |
| `tests/unit/auth-tokens.test.ts`, `tests/unit/login-rate-limit.test.ts`, `tests/unit/server-config-auth.test.ts`, `tests/unit/web-api-base.test.ts` (new) | Unit tests. |
| `tests/integration/auth-api.test.ts` (new) | Guard, login, session and socket behaviour. |
| `apps/web/src/lib/auth.ts` (new) | Token store, `authHeaders`, `onUnauthorized`. |
| `apps/web/src/lib/env.ts`, `apps/web/vite.config.ts` | `VITE_PUBLIC_API_URL`. |
| `apps/web/src/api/client.ts`, `apps/web/src/api/system.ts`, `apps/web/src/features/monitoring/components/BrowserGrid.tsx`, `apps/web/src/features/automation/useLiveEvents.ts` | Carry the token. |
| `apps/web/src/api/auth.ts`, `apps/web/src/features/auth/hooks.ts`, `apps/web/src/features/auth/AuthGate.tsx`, `apps/web/src/pages/Login/LoginPage.tsx`, `apps/web/src/pages/Login/index.ts` (new) | Login flow. |
| `apps/web/src/app/App.tsx`, `apps/web/src/pages/Settings/SettingsPage.tsx` | Mount the gate; sign-out button. |
| `vercel.json` (new), `.env.example`, `README.md` | Deployment and documentation. |

---

### Task 1: Shared error codes, auth errors and auth schemas

**Files:**
- Modify: `packages/shared/src/errors/codes.ts`
- Create: `packages/shared/src/errors/auth-errors.ts`
- Modify: `packages/shared/src/errors/index.ts`
- Create: `packages/shared/src/schemas/auth.ts`
- Modify: `packages/shared/src/schemas/index.ts`
- Test: `tests/unit/auth-schemas.test.ts`

**Interfaces:**
- Consumes: `AppError`, `ERROR_CODES`, `IsoDateTimeSchema` from `@fb/shared`.
- Produces: `ERROR_CODES.AUTH_REQUIRED | AUTH_INVALID | AUTH_RATE_LIMITED`; classes `AuthRequiredError()`, `AuthInvalidError()`, `AuthRateLimitedError(retryAfterSeconds: number)`; schemas `LoginRequestSchema` (`{ password: string }`), `LoginResponseSchema` (`{ token: string; expiresAt: string }`), `AuthSessionSchema` (`{ authRequired: boolean; authenticated: boolean }`) and types `LoginRequest`, `LoginResponse`, `AuthSession`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/auth-schemas.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  AuthInvalidError,
  AuthRateLimitedError,
  AuthRequiredError,
  AuthSessionSchema,
  ERROR_CODES,
  LoginRequestSchema,
  LoginResponseSchema,
} from '@fb/shared';

describe('auth errors', () => {
  it('map to the HTTP statuses the guard relies on', () => {
    expect(new AuthRequiredError()).toMatchObject({ code: ERROR_CODES.AUTH_REQUIRED, status: 401 });
    expect(new AuthInvalidError()).toMatchObject({ code: ERROR_CODES.AUTH_INVALID, status: 401 });
    expect(new AuthRateLimitedError(120)).toMatchObject({
      code: ERROR_CODES.AUTH_RATE_LIMITED,
      status: 429,
      details: { retryAfterSeconds: 120 },
    });
  });
});

describe('auth schemas', () => {
  it('requires a non-empty password', () => {
    expect(LoginRequestSchema.safeParse({ password: '' }).success).toBe(false);
    expect(LoginRequestSchema.safeParse({}).success).toBe(false);
    expect(LoginRequestSchema.safeParse({ password: 'hunter22' }).success).toBe(true);
  });

  it('describes the login response and the session probe', () => {
    expect(
      LoginResponseSchema.safeParse({ token: 'v1.1.abc', expiresAt: '2026-11-07T00:00:00.000Z' })
        .success,
    ).toBe(true);
    expect(AuthSessionSchema.parse({ authRequired: true, authenticated: false })).toEqual({
      authRequired: true,
      authenticated: false,
    });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter @fb/shared build && pnpm vitest run --project unit tests/unit/auth-schemas.test.ts`
Expected: the build fails with `has no exported member 'AuthRequiredError'` or the test fails on the missing exports.

- [ ] **Step 3: Add the codes**

In `packages/shared/src/errors/codes.ts`, after the `// Settings` block and before `} as const;`:

```ts
  // Login
  AUTH_REQUIRED: 'AUTH_REQUIRED',
  AUTH_INVALID: 'AUTH_INVALID',
  AUTH_RATE_LIMITED: 'AUTH_RATE_LIMITED',
```

- [ ] **Step 4: Add the error classes**

Create `packages/shared/src/errors/auth-errors.ts`:

```ts
import { AppError } from './AppError.js';
import { ERROR_CODES } from './codes.js';

/** No token, or a token that does not verify. The client should show the login page. */
export class AuthRequiredError extends AppError {
  constructor() {
    super(ERROR_CODES.AUTH_REQUIRED, 'Sign in to use the control panel', { status: 401 });
  }
}

/** A login attempt with the wrong password. */
export class AuthInvalidError extends AppError {
  constructor() {
    super(ERROR_CODES.AUTH_INVALID, 'Wrong password', { status: 401 });
  }
}

/** Too many wrong passwords in a row. */
export class AuthRateLimitedError extends AppError {
  constructor(retryAfterSeconds: number) {
    super(
      ERROR_CODES.AUTH_RATE_LIMITED,
      `Too many failed logins; try again in ${Math.ceil(retryAfterSeconds / 60)} minute(s)`,
      { status: 429, details: { retryAfterSeconds } },
    );
  }
}
```

In `packages/shared/src/errors/index.ts` add:

```ts
export * from './auth-errors.js';
```

- [ ] **Step 5: Add the schemas**

Create `packages/shared/src/schemas/auth.ts`:

```ts
import { z } from 'zod';
import { IsoDateTimeSchema } from './common.js';

export const LoginRequestSchema = z.object({
  password: z.string().min(1).max(256),
});
export type LoginRequest = z.infer<typeof LoginRequestSchema>;

export const LoginResponseSchema = z.object({
  token: z.string().min(1),
  expiresAt: IsoDateTimeSchema,
});
export type LoginResponse = z.infer<typeof LoginResponseSchema>;

/**
 * What the panel asks before it decides between the login page and the app.
 * `authenticated` reflects the bearer token on the probe itself, so a stored
 * token is validated in the same round trip.
 */
export const AuthSessionSchema = z.object({
  authRequired: z.boolean(),
  authenticated: z.boolean(),
});
export type AuthSession = z.infer<typeof AuthSessionSchema>;
```

In `packages/shared/src/schemas/index.ts` add:

```ts
export * from './auth.js';
```

Check that `IsoDateTimeSchema` is exported from `packages/shared/src/schemas/common.ts` (it is used by `HealthSchema` there); if its export name differs, use the one `HealthSchema.timestamp` uses.

- [ ] **Step 6: Run the test to verify it passes**

Run: `pnpm --filter @fb/shared build && pnpm vitest run --project unit tests/unit/auth-schemas.test.ts`
Expected: 3 tests pass.

- [ ] **Step 7: Commit**

```bash
git add packages/shared/src/errors/codes.ts packages/shared/src/errors/auth-errors.ts packages/shared/src/errors/index.ts packages/shared/src/schemas/auth.ts packages/shared/src/schemas/index.ts tests/unit/auth-schemas.test.ts
git commit -F - <<'EOF'
feat: the shared package knows the three login errors and the login shapes

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 2: Server configuration for the login

**Files:**
- Modify: `apps/server/src/config/env.ts`
- Modify: `apps/server/src/main.ts`
- Modify: `tests/helpers/server.ts`
- Test: `tests/unit/server-config-auth.test.ts`

**Interfaces:**
- Consumes: `loadConfig(source)` from `@fb/server/config`.
- Produces: `AppConfig.auth: { password: string | null; secret: string; secretSource: 'env' | 'generated' }`; `createTestServer({ auth: { password: string; secret?: string } })`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/server-config-auth.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { loadConfig } from '@fb/server/config';

describe('loadConfig auth', () => {
  it('leaves the login off and generates a secret when nothing is set', () => {
    const config = loadConfig({});
    expect(config.auth.password).toBeNull();
    expect(config.auth.secret).toMatch(/^[0-9a-f]{64}$/);
    expect(config.auth.secretSource).toBe('generated');
  });

  it('turns the login on with the given password and secret', () => {
    const config = loadConfig({ AUTH_PASSWORD: 'hunter22', AUTH_SECRET: 'abc123' });
    expect(config.auth).toEqual({ password: 'hunter22', secret: 'abc123', secretSource: 'env' });
  });

  it('treats a blank password as unset', () => {
    expect(loadConfig({ AUTH_PASSWORD: '   ' }).auth.password).toBeNull();
  });

  it('generates a different secret on every load', () => {
    expect(loadConfig({}).auth.secret).not.toBe(loadConfig({}).auth.secret);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project unit tests/unit/server-config-auth.test.ts`
Expected: FAIL, `config.auth` is undefined.

- [ ] **Step 3: Extend the environment schema and AppConfig**

In `apps/server/src/config/env.ts`:

Add at the top, next to the other imports:

```ts
import { randomBytes } from 'node:crypto';
```

Add to `EnvSchema`, after the `SHEETS_TAB` line:

```ts
  // Operator login for remote access. Unset means the API is open, which is
  // only safe while it stays on 127.0.0.1.
  AUTH_PASSWORD: z.string().optional(),
  AUTH_SECRET: z.string().optional(),
```

Add to `AppConfig`, after `sheets`:

```ts
  auth: {
    /** `null` means no login: every route is open. */
    password: string | null;
    /** Signs tokens. A generated one changes on every start. */
    secret: string;
    secretSource: 'env' | 'generated';
  };
```

In `loadConfig`, after `const executablePath = …`:

```ts
  const password = env.AUTH_PASSWORD?.trim();
  const secret = env.AUTH_SECRET?.trim();
```

and add to the returned object, after `sheets: {...}`:

```ts
    auth: {
      password: password === undefined || password === '' ? null : password,
      secret: secret === undefined || secret === '' ? randomBytes(32).toString('hex') : secret,
      secretSource: secret === undefined || secret === '' ? 'generated' : 'env',
    },
```

- [ ] **Step 4: Warn at startup**

In `apps/server/src/main.ts`, after `const container = createContainer(config);` and before `await container.start();`:

```ts
  if (config.auth.password === null) {
    container.logger.warn('API has no login; keep it on 127.0.0.1 and do not expose it', {
      event: 'auth.disabled',
    });
  } else if (config.auth.secretSource === 'generated') {
    container.logger.warn('AUTH_SECRET is unset; every device is logged out at each restart', {
      event: 'auth.secret_generated',
    });
  }
```

- [ ] **Step 5: Teach the test helper**

In `tests/helpers/server.ts`:

Add to the object returned by `testConfig`, after `sheets: {...}`:

```ts
  auth: { password: null, secret: 'test-secret', secretSource: 'env' },
```

Add to `TestServerOptions`:

```ts
  /** Turn the login on for this server. */
  auth?: { password: string; secret?: string };
```

In `createTestServer`, after the `concurrency` line:

```ts
  if (options.auth !== undefined) {
    config.auth = {
      password: options.auth.password,
      secret: options.auth.secret ?? 'test-secret',
      secretSource: 'env',
    };
  }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project unit tests/unit/server-config-auth.test.ts`
Expected: 4 tests pass.

Run: `pnpm typecheck`
Expected: no errors (the `testConfig` object now satisfies the wider `AppConfig`).

- [ ] **Step 7: Commit**

```bash
git add apps/server/src/config/env.ts apps/server/src/main.ts tests/helpers/server.ts tests/unit/server-config-auth.test.ts
git commit -F - <<'EOF'
feat: the server reads AUTH_PASSWORD and AUTH_SECRET, and warns when it runs without them

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 3: Stateless tokens

**Files:**
- Create: `apps/server/src/http/auth/tokens.ts`
- Test: `tests/unit/auth-tokens.test.ts`

**Interfaces:**
- Consumes: `node:crypto`.
- Produces: `TOKEN_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000`; `issueToken(secret: string, nowMs: number): string`; `verifyToken(secret: string, token: string, nowMs: number): boolean`; `tokenExpiry(nowMs: number): string` (ISO date `nowMs + TOKEN_MAX_AGE_MS`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/auth-tokens.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  issueToken,
  TOKEN_MAX_AGE_MS,
  tokenExpiry,
  verifyToken,
} from '../../apps/server/dist/http/auth/tokens.js';

const SECRET = 'correct horse battery staple';
const NOW = Date.UTC(2026, 9, 8, 12, 0, 0);

describe('tokens', () => {
  it('verifies a token it issued', () => {
    const token = issueToken(SECRET, NOW);
    expect(token).toMatch(/^v1\.\d+\.[A-Za-z0-9_-]+$/);
    expect(verifyToken(SECRET, token, NOW + 1_000)).toBe(true);
  });

  it('refuses a token signed with another secret', () => {
    expect(verifyToken('other', issueToken(SECRET, NOW), NOW)).toBe(false);
  });

  it('refuses a tampered token', () => {
    const [version, issuedAt, signature] = issueToken(SECRET, NOW).split('.');
    expect(verifyToken(SECRET, `${version}.${Number(issuedAt) - 1}.${signature}`, NOW)).toBe(false);
    expect(verifyToken(SECRET, `${version}.${issuedAt}.${signature}x`, NOW)).toBe(false);
    expect(verifyToken(SECRET, `${version}.${issuedAt}.${signature}.extra`, NOW)).toBe(false);
  });

  it('expires after thirty days', () => {
    const token = issueToken(SECRET, NOW);
    expect(verifyToken(SECRET, token, NOW + TOKEN_MAX_AGE_MS - 1)).toBe(true);
    expect(verifyToken(SECRET, token, NOW + TOKEN_MAX_AGE_MS)).toBe(false);
  });

  it('refuses garbage without throwing', () => {
    for (const bad of ['', 'v1', 'v1.abc.def', 'v2.1.abc', 'v1..', `v1.${NOW + 60_000}.sig`]) {
      expect(verifyToken(SECRET, bad, NOW)).toBe(false);
    }
  });

  it('reports the expiry as an ISO date', () => {
    expect(tokenExpiry(NOW)).toBe(new Date(NOW + TOKEN_MAX_AGE_MS).toISOString());
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project unit tests/unit/auth-tokens.test.ts`
Expected: FAIL, cannot find module `tokens.js`.

- [ ] **Step 3: Implement**

Create `apps/server/src/http/auth/tokens.ts`:

```ts
import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * A token is `v1.<issuedAtMs>.<signature>`: a signed timestamp, nothing more.
 * The server keeps no session table, so a restart does not log anyone out
 * and there is nothing to garbage-collect. Rotating the secret ends every
 * session at once.
 */
export const TOKEN_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

const VERSION = 'v1';

const sign = (secret: string, issuedAt: string): string =>
  createHmac('sha256', secret).update(`${VERSION}.${issuedAt}`).digest('base64url');

export const issueToken = (secret: string, nowMs: number): string => {
  const issuedAt = String(Math.floor(nowMs));
  return `${VERSION}.${issuedAt}.${sign(secret, issuedAt)}`;
};

export const verifyToken = (secret: string, token: string, nowMs: number): boolean => {
  const parts = token.split('.');
  if (parts.length !== 3) return false;
  const [version, issuedAt, signature] = parts as [string, string, string];
  if (version !== VERSION || !/^\d+$/.test(issuedAt) || signature.length === 0) return false;

  const issuedAtMs = Number(issuedAt);
  if (issuedAtMs > nowMs || nowMs - issuedAtMs >= TOKEN_MAX_AGE_MS) return false;

  const expected = Buffer.from(sign(secret, issuedAt));
  const given = Buffer.from(signature);
  return expected.length === given.length && timingSafeEqual(expected, given);
};

export const tokenExpiry = (nowMs: number): string =>
  new Date(nowMs + TOKEN_MAX_AGE_MS).toISOString();
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project unit tests/unit/auth-tokens.test.ts`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/http/auth/tokens.ts tests/unit/auth-tokens.test.ts
git commit -F - <<'EOF'
feat: a login token is a signed timestamp that lives thirty days

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 4: Login rate limiter and password compare

**Files:**
- Create: `apps/server/src/http/auth/rate-limit.ts`
- Create: `apps/server/src/http/auth/password.ts`
- Test: `tests/unit/login-rate-limit.test.ts`

**Interfaces:**
- Produces: `class LoginRateLimiter { constructor(options?: { limit?: number; windowMs?: number }); isLimited(nowMs: number): boolean; retryAfterMs(nowMs: number): number; recordFailure(nowMs: number): void; reset(): void }` with defaults `limit = 5`, `windowMs = 15 * 60 * 1000`; `passwordMatches(given: string, expected: string): boolean`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/login-rate-limit.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { LoginRateLimiter } from '../../apps/server/dist/http/auth/rate-limit.js';
import { passwordMatches } from '../../apps/server/dist/http/auth/password.js';

const MINUTE = 60_000;

describe('LoginRateLimiter', () => {
  it('allows four failures and blocks on the fifth', () => {
    const limiter = new LoginRateLimiter();
    for (let i = 0; i < 4; i += 1) limiter.recordFailure(i * 1_000);
    expect(limiter.isLimited(5_000)).toBe(false);
    limiter.recordFailure(5_000);
    expect(limiter.isLimited(6_000)).toBe(true);
  });

  it('frees up once the oldest failure leaves the window', () => {
    const limiter = new LoginRateLimiter({ limit: 2, windowMs: 15 * MINUTE });
    limiter.recordFailure(0);
    limiter.recordFailure(MINUTE);
    expect(limiter.isLimited(2 * MINUTE)).toBe(true);
    expect(limiter.retryAfterMs(2 * MINUTE)).toBe(13 * MINUTE);
    expect(limiter.isLimited(15 * MINUTE)).toBe(false);
  });

  it('resets on a successful login', () => {
    const limiter = new LoginRateLimiter({ limit: 1 });
    limiter.recordFailure(0);
    expect(limiter.isLimited(1)).toBe(true);
    limiter.reset();
    expect(limiter.isLimited(2)).toBe(false);
    expect(limiter.retryAfterMs(2)).toBe(0);
  });
});

describe('passwordMatches', () => {
  it('compares exactly, including length', () => {
    expect(passwordMatches('hunter22', 'hunter22')).toBe(true);
    expect(passwordMatches('hunter2', 'hunter22')).toBe(false);
    expect(passwordMatches('hunter22 ', 'hunter22')).toBe(false);
    expect(passwordMatches('', 'hunter22')).toBe(false);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project unit tests/unit/login-rate-limit.test.ts`
Expected: FAIL, cannot find module `rate-limit.js`.

- [ ] **Step 3: Implement the limiter**

Create `apps/server/src/http/auth/rate-limit.ts`:

```ts
/**
 * Counts failed logins in a sliding window. One counter for the whole
 * server: there is a single operator, and a global count cannot be sidestepped
 * with forged forwarding headers the way a per-address count can.
 */
export class LoginRateLimiter {
  private readonly limit: number;
  private readonly windowMs: number;
  private failures: number[] = [];

  constructor(options: { limit?: number; windowMs?: number } = {}) {
    this.limit = options.limit ?? 5;
    this.windowMs = options.windowMs ?? 15 * 60 * 1000;
  }

  private prune(nowMs: number): void {
    this.failures = this.failures.filter((at) => nowMs - at < this.windowMs);
  }

  isLimited(nowMs: number): boolean {
    this.prune(nowMs);
    return this.failures.length >= this.limit;
  }

  /** Milliseconds until the oldest failure in the window ages out; 0 when not limited. */
  retryAfterMs(nowMs: number): number {
    if (!this.isLimited(nowMs)) return 0;
    const oldest = this.failures[0];
    return oldest === undefined ? 0 : Math.max(0, oldest + this.windowMs - nowMs);
  }

  recordFailure(nowMs: number): void {
    this.prune(nowMs);
    this.failures.push(nowMs);
  }

  reset(): void {
    this.failures = [];
  }
}
```

- [ ] **Step 4: Implement the compare**

Create `apps/server/src/http/auth/password.ts`:

```ts
import { createHash, timingSafeEqual } from 'node:crypto';

/**
 * Both sides are hashed first so the comparison runs over equal-length
 * buffers and takes the same time whether the first or the last byte differs.
 */
export const passwordMatches = (given: string, expected: string): boolean => {
  const digest = (value: string): Buffer => createHash('sha256').update(value, 'utf8').digest();
  return timingSafeEqual(digest(given), digest(expected));
};
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project unit tests/unit/login-rate-limit.test.ts`
Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/server/src/http/auth/rate-limit.ts apps/server/src/http/auth/password.ts tests/unit/login-rate-limit.test.ts
git commit -F - <<'EOF'
feat: five wrong passwords in fifteen minutes lock the login, and the compare takes constant time

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 5: Guard, auth routes, and the HTTP integration tests

**Files:**
- Create: `apps/server/src/http/auth/guard.ts`
- Create: `apps/server/src/http/controllers/AuthController.ts`
- Create: `apps/server/src/http/routes/auth.routes.ts`
- Modify: `apps/server/src/http/routes/index.ts`
- Modify: `apps/server/src/app.ts`
- Test: `tests/integration/auth-api.test.ts`

**Interfaces:**
- Consumes: Task 1 errors and schemas; Task 2 `config.auth`; Task 3 `issueToken`, `verifyToken`, `tokenExpiry`; Task 4 `LoginRateLimiter`, `passwordMatches`; `validateBody` from `../middleware/index.js`; `API_PREFIX`, `WEBSOCKET_PATH` from `@fb/shared`.
- Produces: `registerAuthGuard(app: FastifyInstance, auth: AppConfig['auth']): void`; `bearerToken(request: FastifyRequest): string | null`; `class AuthController { constructor(auth: AppConfig['auth'], limiter?: LoginRateLimiter); session; login }`; `authRoutes(controller)`; routes `GET /api/v1/auth/session`, `POST /api/v1/auth/login`.

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/auth-api.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ERROR_CODES, LoginResponseSchema } from '@fb/shared';
import { createTestServer, type TestServer } from '../helpers/server';

const PASSWORD = 'hunter22';

describe('Auth API with the login off', () => {
  let server: TestServer;

  beforeEach(async () => {
    server = await createTestServer();
  });

  afterEach(async () => {
    await server.dispose();
  });

  it('reports that no login is needed and leaves every route open', async () => {
    const session = await server.app.inject({ method: 'GET', url: '/api/v1/auth/session' });
    expect(session.statusCode).toBe(200);
    expect(session.json()).toEqual({ authRequired: false, authenticated: true });

    const accounts = await server.app.inject({ method: 'GET', url: '/api/v1/accounts' });
    expect(accounts.statusCode).toBe(200);
  });

  it('refuses to log in when there is no password to check against', async () => {
    const response = await server.app.inject({
      method: 'POST',
      url: '/api/v1/auth/login',
      payload: { password: 'anything' },
    });
    expect(response.statusCode).toBe(409);
    expect(response.json().error.code).toBe(ERROR_CODES.CONFLICT);
  });
});

describe('Auth API with the login on', () => {
  let server: TestServer;

  beforeEach(async () => {
    server = await createTestServer({ auth: { password: PASSWORD } });
  });

  afterEach(async () => {
    await server.dispose();
  });

  const login = (password: string) =>
    server.app.inject({ method: 'POST', url: '/api/v1/auth/login', payload: { password } });

  it('gates the API but not health, the session probe, or the page', async () => {
    const accounts = await server.app.inject({ method: 'GET', url: '/api/v1/accounts' });
    expect(accounts.statusCode).toBe(401);
    expect(accounts.json().error.code).toBe(ERROR_CODES.AUTH_REQUIRED);

    expect((await server.app.inject({ method: 'GET', url: '/api/v1/health' })).statusCode).toBe(200);

    const session = await server.app.inject({ method: 'GET', url: '/api/v1/auth/session' });
    expect(session.json()).toEqual({ authRequired: true, authenticated: false });

    // No build in the test directory, so the page is a 404, but it is the
    // JSON 404 of a route that was reached, not a 401 from the guard.
    expect((await server.app.inject({ method: 'GET', url: '/' })).statusCode).toBe(404);
    expect((await server.app.inject({ method: 'GET', url: '/assets/app.js' })).statusCode).toBe(404);
    expect((await server.app.inject({ method: 'OPTIONS', url: '/api/v1/accounts' })).statusCode).not.toBe(401);
  });

  it('treats a malformed Authorization header as no token', async () => {
    for (const authorization of ['Basic abc', 'Bearer', 'Bearer ', 'bearer v1.1.x', 'v1.1.x']) {
      const response = await server.app.inject({
        method: 'GET',
        url: '/api/v1/accounts',
        headers: { authorization },
      });
      expect(response.statusCode, authorization).toBe(401);
      expect(response.json().error.code).toBe(ERROR_CODES.AUTH_REQUIRED);
    }
  });

  it('rejects a wrong password and accepts the right one', async () => {
    const wrong = await login('nope');
    expect(wrong.statusCode).toBe(401);
    expect(wrong.json().error.code).toBe(ERROR_CODES.AUTH_INVALID);

    const right = await login(PASSWORD);
    expect(right.statusCode).toBe(200);
    const { token, expiresAt } = LoginResponseSchema.parse(right.json());
    expect(Date.parse(expiresAt)).toBeGreaterThan(Date.now());

    const accounts = await server.app.inject({
      method: 'GET',
      url: '/api/v1/accounts',
      headers: { authorization: `Bearer ${token}` },
    });
    expect(accounts.statusCode).toBe(200);

    const session = await server.app.inject({
      method: 'GET',
      url: '/api/v1/auth/session',
      headers: { authorization: `Bearer ${token}` },
    });
    expect(session.json()).toEqual({ authRequired: true, authenticated: true });
  });

  it('does not count an invalid body as a failed attempt', async () => {
    for (let i = 0; i < 5; i += 1) {
      const response = await server.app.inject({
        method: 'POST',
        url: '/api/v1/auth/login',
        payload: { password: '' },
      });
      expect(response.statusCode).toBe(400);
      expect(response.json().error.code).toBe(ERROR_CODES.VALIDATION_ERROR);
    }
    expect((await login(PASSWORD)).statusCode).toBe(200);
  });

  it('locks the login after five wrong passwords and frees it on a right one later', async () => {
    for (let i = 0; i < 5; i += 1) expect((await login('nope')).statusCode).toBe(401);

    const locked = await login(PASSWORD);
    expect(locked.statusCode).toBe(429);
    expect(locked.json().error.code).toBe(ERROR_CODES.AUTH_RATE_LIMITED);
    expect(locked.json().error.details.retryAfterSeconds).toBeGreaterThan(0);
  });

  it('rejects a token signed with another secret', async () => {
    const other = await createTestServer({ auth: { password: PASSWORD, secret: 'other-secret' } });
    try {
      const foreign = LoginResponseSchema.parse(
        (
          await other.app.inject({
            method: 'POST',
            url: '/api/v1/auth/login',
            payload: { password: PASSWORD },
          })
        ).json(),
      ).token;

      const response = await server.app.inject({
        method: 'GET',
        url: '/api/v1/accounts',
        headers: { authorization: `Bearer ${foreign}` },
      });
      expect(response.statusCode).toBe(401);
    } finally {
      await other.dispose();
    }
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project integration tests/integration/auth-api.test.ts`
Expected: the first `describe` fails on `/api/v1/auth/session` returning 404; the second fails on the guard (200 instead of 401).

- [ ] **Step 3: Implement the guard**

Create `apps/server/src/http/auth/guard.ts`:

```ts
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { API_PREFIX, AuthRequiredError, WEBSOCKET_PATH } from '@fb/shared';
import type { AppConfig } from '../../config/index.js';
import { verifyToken } from './tokens.js';

const BEARER = /^Bearer\s+(\S+)$/;

/** The token from `Authorization: Bearer …`, or null when absent or malformed. */
export const bearerToken = (request: FastifyRequest): string | null => {
  const header = request.headers.authorization;
  if (typeof header !== 'string') return null;
  const match = BEARER.exec(header);
  return match?.[1] ?? null;
};

/** Browsers cannot set headers on a WebSocket, so the socket carries `?token=`. */
const queryToken = (request: FastifyRequest): string | null => {
  const query = request.query as Record<string, unknown> | undefined;
  const token = query?.['token'];
  return typeof token === 'string' && token.length > 0 ? token : null;
};

const pathOf = (url: string): string => url.split('?')[0] ?? url;

/**
 * Every `/api/v1/*` route and the `/ws` upgrade need a valid token. Health,
 * the auth routes, CORS preflights and the static page stay open, so a phone
 * can load the panel and reach the login screen before it has a token.
 *
 * When the config has no password the hook is not installed at all.
 */
export const registerAuthGuard = (app: FastifyInstance, auth: AppConfig['auth']): void => {
  const password = auth.password;
  if (password === null) return;

  app.addHook('onRequest', (request, _reply, done) => {
    if (request.method === 'OPTIONS') return done();

    const path = pathOf(request.url);
    const isSocket = path === WEBSOCKET_PATH;
    if (!isSocket && !path.startsWith(`${API_PREFIX}/`)) return done();
    if (path === `${API_PREFIX}/health` || path.startsWith(`${API_PREFIX}/auth/`)) return done();

    const token = isSocket ? queryToken(request) : bearerToken(request);
    if (token !== null && verifyToken(auth.secret, token, Date.now())) return done();

    return done(new AuthRequiredError());
  });
};
```

- [ ] **Step 4: Implement the controller and routes**

Create `apps/server/src/http/controllers/AuthController.ts`:

```ts
import type { FastifyReply, FastifyRequest } from 'fastify';
import {
  AppError,
  AuthInvalidError,
  AuthRateLimitedError,
  ERROR_CODES,
  LoginRequestSchema,
  type AuthSession,
  type LoginResponse,
} from '@fb/shared';
import type { AppConfig } from '../../config/index.js';
import { bearerToken } from '../auth/guard.js';
import { passwordMatches } from '../auth/password.js';
import { LoginRateLimiter } from '../auth/rate-limit.js';
import { issueToken, tokenExpiry, verifyToken } from '../auth/tokens.js';
import { validateBody } from '../middleware/index.js';

/** The two routes the guard leaves open: a probe and the login itself. */
export class AuthController {
  constructor(
    private readonly auth: AppConfig['auth'],
    private readonly limiter: LoginRateLimiter = new LoginRateLimiter(),
    private readonly now: () => number = Date.now,
  ) {}

  session = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const token = bearerToken(request);
    const body: AuthSession =
      this.auth.password === null
        ? { authRequired: false, authenticated: true }
        : {
            authRequired: true,
            authenticated: token !== null && verifyToken(this.auth.secret, token, this.now()),
          };
    await reply.status(200).send(body);
  };

  login = async (request: FastifyRequest, reply: FastifyReply): Promise<void> => {
    const { password } = validateBody(LoginRequestSchema, request);
    const expected = this.auth.password;
    if (expected === null) {
      throw new AppError(ERROR_CODES.CONFLICT, 'Login is not configured on this server', {
        status: 409,
      });
    }

    const now = this.now();
    if (this.limiter.isLimited(now)) {
      throw new AuthRateLimitedError(Math.ceil(this.limiter.retryAfterMs(now) / 1000));
    }
    if (!passwordMatches(password, expected)) {
      this.limiter.recordFailure(now);
      throw new AuthInvalidError();
    }

    this.limiter.reset();
    const body: LoginResponse = { token: issueToken(this.auth.secret, now), expiresAt: tokenExpiry(now) };
    await reply.status(200).send(body);
  };
}
```

Create `apps/server/src/http/routes/auth.routes.ts`:

```ts
import type { FastifyInstance } from 'fastify';
import type { AuthController } from '../controllers/AuthController.js';

export const authRoutes =
  (controller: AuthController) =>
  async (app: FastifyInstance): Promise<void> => {
    app.get('/auth/session', controller.session);
    app.post('/auth/login', controller.login);
  };
```

In `apps/server/src/http/routes/index.ts`:

Add imports:

```ts
import { AuthController } from '../controllers/AuthController.js';
import { authRoutes } from './auth.routes.js';
```

After `const health = new HealthController(container.health);` add:

```ts
  const auth = new AuthController(container.config.auth);
```

Inside the `app.register(async (api) => { … })` block, after `await api.register(healthRoutes(health));` add:

```ts
      await api.register(authRoutes(auth));
```

- [ ] **Step 5: Install the guard**

In `apps/server/src/app.ts`:

Add import:

```ts
import { registerAuthGuard } from './http/auth/guard.js';
```

After `registerErrorHandler(app, container.logger, container.config.isProduction);` and before `await registerWebSocket(app, container);` add:

```ts
  registerAuthGuard(app, container.config.auth);
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project integration tests/integration/auth-api.test.ts`
Expected: 8 tests pass.

Run: `pnpm --filter @fb/server build && pnpm test`
Expected: every existing unit and integration test still passes (login is off in `testConfig`).

- [ ] **Step 7: Commit**

```bash
git add apps/server/src/http/auth/guard.ts apps/server/src/http/controllers/AuthController.ts apps/server/src/http/routes/auth.routes.ts apps/server/src/http/routes/index.ts apps/server/src/app.ts tests/integration/auth-api.test.ts
git commit -F - <<'EOF'
feat: the API asks for a password when one is configured, and hands out a token that opens every route

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 6: The WebSocket upgrade honours the token

**Files:**
- Modify: `tests/integration/auth-api.test.ts`
- Possibly modify: `apps/server/src/http/auth/guard.ts` (only if Step 2 shows the upgrade is not refused)

**Interfaces:**
- Consumes: Task 5 guard; Node 22 global `WebSocket`; `server.app.listen({ host: '127.0.0.1', port: 0 })` and `server.app.server.address()`.
- Produces: nothing new; proves `/ws?token=` works and bare `/ws` is refused.

- [ ] **Step 1: Write the failing test**

Append to the `describe('Auth API with the login on', …)` block in `tests/integration/auth-api.test.ts`:

```ts
  describe('WebSocket', () => {
    const listen = async (): Promise<string> => {
      await server.app.listen({ host: '127.0.0.1', port: 0 });
      const address = server.app.server.address();
      if (address === null || typeof address === 'string') throw new Error('No TCP address');
      return `ws://127.0.0.1:${address.port}/ws`;
    };

    const openSocket = (url: string): Promise<'open' | 'refused'> =>
      new Promise((resolve) => {
        const socket = new WebSocket(url);
        socket.onopen = () => {
          socket.close();
          resolve('open');
        };
        socket.onerror = () => resolve('refused');
      });

    it('refuses an upgrade without a token and accepts one with it', async () => {
      const base = await listen();
      expect(await openSocket(base)).toBe('refused');
      expect(await openSocket(`${base}?token=v1.1.forged`)).toBe('refused');

      const { token } = LoginResponseSchema.parse((await login(PASSWORD)).json());
      expect(await openSocket(`${base}?token=${encodeURIComponent(token)}`)).toBe('open');
    });
  });
```

- [ ] **Step 2: Run the test to verify it fails or passes**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project integration tests/integration/auth-api.test.ts -t WebSocket`

Expected if the guard already aborts the upgrade: PASS, go to Step 4.
Expected otherwise: the first `expect` fails with `'open'` instead of `'refused'`; go to Step 3.

- [ ] **Step 3: Only if Step 2 failed: refuse the upgrade explicitly**

`@fastify/websocket` performs the upgrade after the `onRequest` hooks when no reply was sent. If passing an error to `done` did not stop it, send the reply in the hook instead. In `apps/server/src/http/auth/guard.ts` replace the last line of the hook:

```ts
    return done(new AuthRequiredError());
```

with:

```ts
    const error = new AuthRequiredError();
    void _reply.status(error.status).send({ error: error.toJSON() });
    return done();
```

and rename `_reply` to `reply` in the hook signature. Rebuild and run Step 2 again; it must pass now.

- [ ] **Step 4: Run the whole file**

Run: `pnpm --filter @fb/server build && pnpm vitest run --project integration tests/integration/auth-api.test.ts`
Expected: 9 tests pass. `dispose()` closes the listening server, so no port is left open.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/auth-api.test.ts apps/server/src/http/auth/guard.ts
git commit -F - <<'EOF'
test: a live-events socket without a valid token never opens

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 7: The web app carries the token on every network path

**Files:**
- Create: `apps/web/src/lib/auth.ts`
- Create: `apps/web/src/lib/api-base.ts`
- Modify: `apps/web/src/lib/env.ts`
- Modify: `apps/web/vite.config.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/system.ts`
- Modify: `apps/web/src/features/monitoring/components/BrowserGrid.tsx`
- Modify: `apps/web/src/features/automation/useLiveEvents.ts`
- Test: `tests/unit/web-api-base.test.ts`

**Interfaces:**
- Produces: `getToken(): string | null`, `setToken(token: string): void`, `clearToken(): void`, `authHeaders(): Record<string, string>`, `onUnauthorized(listener: () => void): () => void`, `reportUnauthorized(): void` in `lib/auth.ts`; `normaliseApiBase(value: string | undefined): string` in `lib/api-base.ts`; `WEB_CONFIG.apiBaseUrl` now reads `VITE_PUBLIC_API_URL`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/web-api-base.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { normaliseApiBase } from '../../apps/web/src/lib/api-base';

describe('normaliseApiBase', () => {
  it('is empty, meaning same-origin, when nothing is configured', () => {
    expect(normaliseApiBase(undefined)).toBe('');
    expect(normaliseApiBase('')).toBe('');
    expect(normaliseApiBase('   ')).toBe('');
  });

  it('drops a trailing slash so paths never double it', () => {
    expect(normaliseApiBase('https://pc.tail1234.ts.net/')).toBe('https://pc.tail1234.ts.net');
    expect(normaliseApiBase('https://pc.tail1234.ts.net')).toBe('https://pc.tail1234.ts.net');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm vitest run --project unit tests/unit/web-api-base.test.ts`
Expected: FAIL, cannot find module `api-base`.

- [ ] **Step 3: Implement the base URL helper and env**

Create `apps/web/src/lib/api-base.ts`:

```ts
/** Empty means same-origin. Anything else is an origin with no trailing slash. */
export const normaliseApiBase = (value: string | undefined): string => {
  const trimmed = (value ?? '').trim();
  return trimmed.replace(/\/+$/, '');
};
```

Replace `apps/web/src/lib/env.ts` with:

```ts
import { normaliseApiBase } from './api-base';

/**
 * Vite inlines these at build time. Reading them in one module keeps
 * import.meta.env out of the rest of the app.
 */
export const WEB_CONFIG = {
  /**
   * Same-origin by default: the dev server proxies /api to the backend and
   * the API serves the built app itself. A static host such as Vercel sets
   * VITE_PUBLIC_API_URL to the API's public origin at build time.
   */
  apiBaseUrl: normaliseApiBase(import.meta.env['VITE_PUBLIC_API_URL']),
  isDev: import.meta.env.DEV,
} as const;
```

In `apps/web/vite.config.ts` replace the `define` block:

```ts
    define: {
      // The bundle talks to a same-origin /api; the dev server proxies it.
      'import.meta.env.VITE_API_URL': JSON.stringify(''),
    },
```

with:

```ts
    define: {
      // Empty keeps the bundle same-origin (dev proxy, or the API serving its
      // own build). A static host sets VITE_PUBLIC_API_URL to the API origin.
      'import.meta.env.VITE_PUBLIC_API_URL': JSON.stringify(read('VITE_PUBLIC_API_URL', '')),
    },
```

- [ ] **Step 4: Implement the token store**

Create `apps/web/src/lib/auth.ts`:

```ts
const STORAGE_KEY = 'fb.auth.token';

const listeners = new Set<() => void>();

export const getToken = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};

export const setToken = (token: string): void => {
  try {
    localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Private window or storage disabled: the session lasts until reload.
  }
};

export const clearToken = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
};

/** Headers to merge into any fetch that reaches the API. Empty when signed out. */
export const authHeaders = (): Record<string, string> => {
  const token = getToken();
  return token === null ? {} : { authorization: `Bearer ${token}` };
};

/** Called when the server answers AUTH_REQUIRED: the stored token is gone. */
export const onUnauthorized = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const reportUnauthorized = (): void => {
  clearToken();
  for (const listener of listeners) listener();
};
```

- [ ] **Step 5: Send the token from the JSON client**

In `apps/web/src/api/client.ts`:

Add import:

```ts
import { authHeaders, reportUnauthorized } from '../lib/auth';
```

Replace the `fetch` call's `headers` line:

```ts
    headers: body === undefined ? {} : { 'content-type': 'application/json' },
```

with:

```ts
    headers: {
      ...authHeaders(),
      ...(body === undefined ? {} : { 'content-type': 'application/json' }),
    },
```

Inside `if (!response.ok) {`, before `const parsed = ApiErrorSchema.safeParse(payload);` add:

```ts
    if (response.status === 401) {
      const code = ApiErrorSchema.safeParse(payload);
      // AUTH_INVALID is a wrong password on the login form and stays there;
      // AUTH_REQUIRED means the token is gone and the gate must take over.
      if (code.success && code.data.error.code === ERROR_CODES.AUTH_REQUIRED) reportUnauthorized();
    }
```

- [ ] **Step 6: Send the token from the upload, the screenshot and the socket**

In `apps/web/src/api/system.ts`, add the import `import { authHeaders } from '../lib/auth';` and change the upload fetch:

```ts
  const response = await fetch(`${WEB_CONFIG.apiBaseUrl}${API_PREFIX}/media`, {
    method: 'POST',
    headers: authHeaders(),
    body,
  });
```

In `apps/web/src/features/monitoring/components/BrowserGrid.tsx`, add the import `import { authHeaders } from '@/lib/auth';` and change the screenshot fetch:

```ts
        const response = await fetch(`${url}?t=${Date.now()}`, {
          cache: 'no-store',
          headers: authHeaders(),
        });
```

In `apps/web/src/features/automation/useLiveEvents.ts`, add the import `import { getToken } from '../../lib/auth';` and replace `socketUrl`:

```ts
const socketUrl = (): string => {
  const base = WEB_CONFIG.apiBaseUrl === '' ? window.location.origin : WEB_CONFIG.apiBaseUrl;
  const url = new URL(WEBSOCKET_PATH, base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  // A browser cannot set headers on a socket, so the token rides the query.
  const token = getToken();
  if (token !== null) url.searchParams.set('token', token);
  return url.toString();
};
```

- [ ] **Step 7: Verify**

Run: `pnpm vitest run --project unit tests/unit/web-api-base.test.ts`
Expected: 2 tests pass.

Run: `pnpm --filter @fb/web typecheck && pnpm lint`
Expected: no errors.

Run: `pnpm --filter @fb/web build && grep -c "fb.auth.token" apps/web/dist/assets/index-*.js`
Expected: `1` or more, proving the store is in the bundle; the bundle contains no `VITE_PUBLIC_API_URL` string because `define` inlined an empty string.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/lib/auth.ts apps/web/src/lib/api-base.ts apps/web/src/lib/env.ts apps/web/vite.config.ts apps/web/src/api/client.ts apps/web/src/api/system.ts apps/web/src/features/monitoring/components/BrowserGrid.tsx apps/web/src/features/automation/useLiveEvents.ts tests/unit/web-api-base.test.ts
git commit -F - <<'EOF'
feat: the panel keeps a login token and sends it with every request, upload, screenshot and socket

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 8: Login page, session gate, sign out

**Files:**
- Create: `apps/web/src/api/auth.ts`
- Modify: `apps/web/src/api/index.ts`
- Create: `apps/web/src/features/auth/hooks.ts`
- Create: `apps/web/src/features/auth/AuthGate.tsx`
- Create: `apps/web/src/pages/Login/LoginPage.tsx`
- Create: `apps/web/src/pages/Login/index.ts`
- Modify: `apps/web/src/app/App.tsx`
- Modify: `apps/web/src/pages/Settings/SettingsPage.tsx`

**Interfaces:**
- Consumes: Task 1 `AuthSessionSchema`, `LoginResponseSchema`, `LoginRequest`; Task 7 `setToken`, `clearToken`, `onUnauthorized`, `getToken`; `apiRequest` from `./client`; `Button`, `Card*`, `TextField`, `ErrorNotice` components already in the app.
- Produces: `getSession(signal?)`, `login(password)` in `api/auth.ts`; `useSession()` (query key `['auth-session']`); `<AuthGate>` wrapping children; `<LoginPage onSignedIn={() => void} />`.

- [ ] **Step 1: API module and hook**

Create `apps/web/src/api/auth.ts`:

```ts
import { AuthSessionSchema, LoginResponseSchema, type AuthSession, type LoginResponse } from '@fb/shared';
import { apiRequest } from './client';

export const getSession = (signal?: AbortSignal): Promise<AuthSession> =>
  apiRequest('/auth/session', AuthSessionSchema, { signal });

export const login = (password: string): Promise<LoginResponse> =>
  apiRequest('/auth/login', LoginResponseSchema, { method: 'POST', body: { password } });
```

In `apps/web/src/api/index.ts` add `export * from './auth';`.

Create `apps/web/src/features/auth/hooks.ts`:

```ts
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import type { AuthSession } from '@fb/shared';
import { getSession } from '../../api/auth';

/** Asked once per page load; the gate refetches it after a login or a 401. */
export const useSession = (): UseQueryResult<AuthSession> =>
  useQuery({
    queryKey: ['auth-session'],
    queryFn: ({ signal }) => getSession(signal),
    staleTime: Infinity,
    retry: 1,
  });
```

- [ ] **Step 2: Login page**

Create `apps/web/src/pages/Login/LoginPage.tsx`:

```tsx
import { useState, type FormEvent, type ReactElement } from 'react';
import { useMutation } from '@tanstack/react-query';
import { login } from '../../api/auth';
import { setToken } from '../../lib/auth';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorNotice } from '@/components/common/Feedback';
import { TextField } from '@/components/forms/Field';

/** One password for the one operator. The server rate-limits wrong guesses. */
export const LoginPage = ({ onSignedIn }: { onSignedIn: () => void }): ReactElement => {
  const [password, setPassword] = useState('');
  const attempt = useMutation({
    mutationFn: login,
    onSuccess: ({ token }) => {
      setToken(token);
      onSignedIn();
    },
  });

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (password.length === 0 || attempt.isPending) return;
    attempt.mutate(password);
  };

  return (
    <main className="flex min-h-svh items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>FB Automation</CardTitle>
          <CardDescription>Enter the control panel password.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={submit}>
            <TextField
              label="Password"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {attempt.error !== null && <ErrorNotice error={attempt.error} title="Not signed in" />}
            <Button type="submit" disabled={password.length === 0 || attempt.isPending}>
              {attempt.isPending ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
};
```

Create `apps/web/src/pages/Login/index.ts`:

```ts
export { LoginPage } from './LoginPage';
```

- [ ] **Step 3: The gate**

Create `apps/web/src/features/auth/AuthGate.tsx`:

```tsx
import { useEffect, type ReactElement, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ErrorNotice } from '@/components/common/Feedback';
import { onUnauthorized } from '../../lib/auth';
import { LoginPage } from '../../pages/Login';
import { useSession } from './hooks';

/**
 * Decides between the login page and the app, once per page load. A 401 from
 * anywhere in the app clears the token and brings the login page back.
 */
export const AuthGate = ({ children }: { children: ReactNode }): ReactElement => {
  const queryClient = useQueryClient();
  const session = useSession();

  const refresh = (): void => {
    void queryClient.invalidateQueries({ queryKey: ['auth-session'] });
  };

  useEffect(() => onUnauthorized(() => {
    queryClient.clear();
    refresh();
  }), [queryClient]);

  if (session.isPending) return <div className="min-h-svh bg-background" aria-busy="true" />;
  if (session.isError) {
    return (
      <main className="flex min-h-svh items-center justify-center p-4">
        <div className="w-full max-w-sm">
          <ErrorNotice error={session.error} title="PC unreachable" />
        </div>
      </main>
    );
  }
  if (session.data.authRequired && !session.data.authenticated) {
    return <LoginPage onSignedIn={refresh} />;
  }
  return <>{children}</>;
};
```

Note on the hook rule: `refresh` is defined inside the component and used in the effect; ESLint's `react-hooks/exhaustive-deps` may ask for it in the dependency list. If it does, move `refresh` inside the effect body and call `queryClient.invalidateQueries` directly there and in the `onSignedIn` prop.

- [ ] **Step 4: Mount the gate and add sign out**

Replace `apps/web/src/app/App.tsx` with:

```tsx
import type { ReactElement } from 'react';
import { RouterProvider } from 'react-router-dom';
import { AuthGate } from '../features/auth/AuthGate';
import { AppProviders } from './providers';
import { router } from './router';

export const App = (): ReactElement => (
  <AppProviders>
    <AuthGate>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </AuthGate>
  </AppProviders>
);
```

In `apps/web/src/pages/Settings/SettingsPage.tsx`:

Add imports:

```ts
import { clearToken } from '../../lib/auth';
import { useSession } from '../../features/auth/hooks';
```

Inside `SettingsPage`, after `const update = useUpdateSettings();` add:

```ts
  const session = useSession();
```

After the closing `</form>` and before the closing `</div>` of the page add:

```tsx
      {session.data?.authRequired === true && (
        <Card>
          <CardHeader>
            <CardTitle>Remote access</CardTitle>
            <CardDescription>
              This device holds a sign-in token for thirty days. Signing out forgets it here only.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                clearToken();
                window.location.reload();
              }}
            >
              Sign out
            </Button>
          </CardContent>
        </Card>
      )}
```

- [ ] **Step 5: Typecheck, lint, build**

Run: `pnpm --filter @fb/web typecheck && pnpm lint && pnpm --filter @fb/web build`
Expected: no errors. Fix any `exhaustive-deps` warning as described in Step 3.

- [ ] **Step 6: Drive it in the real app**

With the dev console closed (no other server on 3001), in a scratch shell at the repository root:

```powershell
$env:AUTH_PASSWORD = 'hunter22'; $env:AUTH_SECRET = 'dev-secret'
pnpm dev
```

Then, from another shell:

```powershell
Invoke-WebRequest http://127.0.0.1:5173/api/v1/accounts -UseBasicParsing   # expect 401
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5173/api/v1/auth/login -ContentType application/json -Body '{"password":"hunter22"}'
Invoke-WebRequest http://127.0.0.1:5173/api/v1/accounts -UseBasicParsing -Headers @{ authorization = "Bearer $($r.token)" }  # expect 200
```

Open `http://localhost:5173` in a browser: the login card appears; a wrong password shows "Wrong password"; the right one opens the dashboard and the connection badge turns live (socket open with the token). Settings shows "Remote access" with Sign out; Sign out returns the login card. Stop `pnpm dev` and clear the two variables.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/api/auth.ts apps/web/src/api/index.ts apps/web/src/features/auth/hooks.ts apps/web/src/features/auth/AuthGate.tsx apps/web/src/pages/Login/LoginPage.tsx apps/web/src/pages/Login/index.ts apps/web/src/app/App.tsx apps/web/src/pages/Settings/SettingsPage.tsx
git commit -F - <<'EOF'
feat: the panel shows a login card until it holds a token, and a 401 brings it back

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 9: Vercel configuration and documentation

**Files:**
- Create: `vercel.json`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 7's `VITE_PUBLIC_API_URL`.
- Produces: a Vercel build that outputs `apps/web/dist` from the repository root.

- [ ] **Step 1: vercel.json**

Create `vercel.json` at the repository root:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "installCommand": "pnpm install --frozen-lockfile",
  "buildCommand": "pnpm build:packages && pnpm --filter @fb/web build",
  "outputDirectory": "apps/web/dist",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

- [ ] **Step 2: Prove the build command works from a clean checkout**

```bash
git stash --include-untracked --quiet || true
pnpm install --frozen-lockfile && pnpm build:packages && pnpm --filter @fb/web build && test -f apps/web/dist/index.html && echo BUILD OK
git stash pop --quiet || true
```

Expected: `BUILD OK`. (The stash lines only matter if the tree is dirty; with everything committed they are no-ops.)

- [ ] **Step 3: .env.example**

In `.env.example`, after the `CORS_ORIGIN` line, change the comment and value to:

```ini
# Comma-separated list of origins allowed to call the API. Add the Vercel
# origin when the panel is served from there.
CORS_ORIGIN=http://localhost:5173,https://fbtool-phi.vercel.app
```

Append a new section at the end:

```ini
# ---------------------------------------------------------------------------
# Remote access (see README, "Remote access")
# ---------------------------------------------------------------------------
# When set, every API call needs a token from POST /api/v1/auth/login. Leave
# unset only while the API is reachable from this PC alone.
AUTH_PASSWORD=
# Signs the tokens. Generate once: node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
# Unset means a new secret per start, which signs every device out at restart.
AUTH_SECRET=
# Build-time only, for a static host such as Vercel: the public origin of the
# API, e.g. https://desktop-uqs51mj.tail1234.ts.net . Leave unset here.
# VITE_PUBLIC_API_URL=
```

- [ ] **Step 4: README**

In `README.md`, under "Not ported from the old system", delete the bullet:

```
- Web password authentication for remote access. The API binds to
  `127.0.0.1` by default and has no login of its own.
```

Add a new section before "Not ported from the old system":

````markdown
## Remote access

The API stays on `127.0.0.1`. To reach it from a phone, Tailscale Funnel
publishes it at `https://<pc>.<tailnet>.ts.net`, and a password protects it.

1. Set `AUTH_PASSWORD` and `AUTH_SECRET` in `.env` (see `.env.example`), and
   add the panel's origin to `CORS_ORIGIN`. Restart the server.
2. On the PC, once:

   ```
   winget install --id tailscale.tailscale -e
   tailscale up
   tailscale funnel --bg 3001
   ```

   `tailscale up` opens a browser login. The first `tailscale funnel` prints a
   link to enable Funnel for the tailnet; follow it, then run the command
   again. `tailscale funnel status` shows the public URL. The Funnel survives
   reboots.
3. Open the URL from step 2 on any device: the API serves the built panel at
   `/`, and the login page asks for `AUTH_PASSWORD`.

To serve the panel from Vercel as well, the project builds this repository's
`main` with `vercel.json`. In the Vercel project settings, leave Root
Directory empty and set the Production environment variable
`VITE_PUBLIC_API_URL` to the Funnel URL from step 2. The Vercel page then
talks to the API on the PC directly; the PC must be on and the server running.

Tokens last thirty days. Changing `AUTH_SECRET` signs every device out.
Five wrong passwords lock the login for fifteen minutes.
````

- [ ] **Step 5: Format check and commit**

Run: `pnpm format:check`
Expected: no complaints about the edited files (run `pnpm prettier --write vercel.json README.md .env.example` if there are).

```bash
git add vercel.json .env.example README.md
git commit -F - <<'EOF'
docs: Vercel builds the panel from the repository root, and the README explains remote access

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 10: Put it live, operator steps

This task is operations, not code. The implementer runs the commands that need no account, and hands the operator the two browser logins.

**Files:** none in the repository. `.env` on the PC (gitignored) is edited.

- [ ] **Step 1: Secrets into `.env`**

```powershell
$secret = node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

Edit `.env` (not `.env.example`): set `AUTH_PASSWORD` to a value the operator chooses (ask them; never invent one), `AUTH_SECRET` to `$secret`, and `CORS_ORIGIN=http://localhost:5173,https://fbtool-phi.vercel.app`.

- [ ] **Step 2: Tailscale**

```powershell
winget install --id tailscale.tailscale -e
```

Ask the operator to run `tailscale up` themselves (browser login). Then:

```powershell
tailscale funnel --bg 3001
```

If it prints a link to enable Funnel, the operator opens it, approves, and the command is run again. Then:

```powershell
tailscale funnel status
```

Expected: a line like `https://desktop-uqs51mj.tail1234.ts.net (Funnel on)` → `http://127.0.0.1:3001`. Record the URL.

- [ ] **Step 3: Start the server as the operator's user and check it through the Funnel**

Restart the dev console (`pnpm dev`) or whatever runs the server, so the new `.env` is read. Then from any shell:

```powershell
Invoke-WebRequest https://<funnel-host>/api/v1/health -UseBasicParsing          # 200
Invoke-WebRequest https://<funnel-host>/api/v1/accounts -UseBasicParsing        # 401
```

- [ ] **Step 4: Vercel project settings**

In the Vercel dashboard, project `fbtool` (account `mrkbyln1508`): Settings → General → Root Directory: clear it (it is `web`) and save. Settings → Environment Variables: add `VITE_PUBLIC_API_URL` = the Funnel URL, Production only. Then Deployments → Redeploy the latest `main` commit.

Check from the shell:

```bash
gh api 'repos/bylnmrk-ggwp/FB-TOOL-AUTOMATION/deployments?per_page=1' --jq '.[0].id' | xargs -I{} gh api 'repos/bylnmrk-ggwp/FB-TOOL-AUTOMATION/deployments/{}/statuses?per_page=1' --jq '.[0].state'
```

Expected: `success`.

```powershell
(Invoke-WebRequest https://fbtool-phi.vercel.app/ -UseBasicParsing).Content -match '<title>FB Automation</title>'
```

Expected: `True` (the old page said "MCARSPH AutoShare").

- [ ] **Step 5: Acceptance on a phone, mobile data, not Wi-Fi**

Open `https://fbtool-phi.vercel.app`: login card. Wrong password: "Wrong password". Right password: dashboard, connection badge live. Monitor page: thumbnails load while a browser session runs. Settings → Sign out → login card returns. Reload: still the login card (token cleared).

- [ ] **Step 6: Record**

No commit. Note the Funnel URL in the operator's own notes; it is not committed anywhere.

---

## Self-review notes

- Spec coverage: Part 1 → Tasks 1–6; Part 2 → Tasks 7–8; Part 3 → Tasks 9–10; Part 4 → Tasks 9–10; Part 5 → Tasks 1–8 tests plus Task 10 acceptance.
- Review Focus 1–5 are pinned by tests in Tasks 5, 3, 5, 7 and 5 respectively.
- Names used across tasks: `registerAuthGuard`, `bearerToken`, `verifyToken`, `issueToken`, `tokenExpiry`, `TOKEN_MAX_AGE_MS`, `LoginRateLimiter`, `passwordMatches`, `AuthController`, `authRoutes`, `authHeaders`, `getToken`, `setToken`, `clearToken`, `onUnauthorized`, `reportUnauthorized`, `normaliseApiBase`, `getSession`, `login`, `useSession`, `AuthGate`, `LoginPage`. Each is defined in exactly one task and used with the same signature afterwards.
