# Automation

Playwright drives real browsers against persistent profiles. Everything in this
document lives in `packages/automation`, behind the `AutomationGateway`
interface declared in `packages/domain`.

## Browser lifecycle

```
start(accountId)
  ├─ ProfileManager.ensure(slug)        → creates data/browser-profiles/<slug>
  ├─ ProfileLockManager.acquire(...)    → database row + lock file, or refuse
  ├─ BrowserLauncher.launch(...)        → launchPersistentContext
  ├─ BrowserContextManager.prepare(...) → default timeouts, one page, listeners
  └─ BrowserManager registry            → in-memory session, status → online
```

```
stop(accountId)
  ├─ status → stopping
  ├─ context.close()
  ├─ ProfileLockManager.release(...)
  └─ registry delete, status → offline
```

`BrowserManager` is the only holder of live browser objects. It is a plain
in-memory map: a process handle has no meaning after a restart, so writing one
to the database would only create lies to clean up later.

## Persistent profiles

Each account owns one directory:

```
data/browser-profiles/
├── account-001/
├── account-002/
└── account-003/
```

Playwright's `launchPersistentContext` points at that directory, so cookies,
local storage and the logged-in session survive a stop and start. A profile is
created once, when the account is created, and removed when the account is
deleted.

The slug is validated against `/^[a-z0-9][a-z0-9-]*$/` and joined to the
configured root through `resolveInside()`, which refuses anything that resolves
outside it. That is the only way a profile path is ever constructed.

## Profile locking

Two workers driving the same profile directory corrupts it. A lock is therefore
required before launch and is held for the life of the session.

- **Where:** a `locked_by` / `locked_at` pair on `browser_profiles`, plus a
  `.lock` file inside the profile directory holding the owning pid.
- **Owner:** `"<pid>:<sessionId>"`.
- **TTL:** `PROFILE_LOCK_TTL_MS`, refreshed while the session lives.
- **Acquire:** a single conditional `UPDATE` that succeeds only when the lock is
  free or already expired. Losing that race raises `ProfileLockedError`.

Failure modes and what happens:

| Situation              | Handling                                                                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Browser crashes        | Playwright `close` event fires; the session is dropped, the lock released, the account marked `error`.                         |
| User closes the window | Same path as a crash — the close event is the trigger either way.                                                              |
| Process killed         | Neither handler runs. On the next start the lock is past its TTL, and the recorded pid is gone, so it is broken and reclaimed. |
| Application restart    | `releaseLocksOwnedBy(pid)` runs at startup for locks this machine wrote, and `reapStale()` clears the rest.                    |
| Graceful shutdown      | `BrowserManager.stopAll()` closes every context and releases every lock before the process exits.                              |

## The gateway

```ts
interface AutomationGateway {
  execute(action: AutomationAction, context: AutomationContext): Promise<AutomationResult>;
}
```

`AutomationContext` carries the job id, the session id, a progress callback, an
`AbortSignal` for cancellation, a timeout and the human-like delay range. The
queue depends on this interface, so job execution can be tested against a fake
gateway with no browser at all.

## Facebook implementation

```
facebook/
├── FacebookAutomation.ts     — implements AutomationGateway, dispatches on action.type
├── FacebookNavigation.ts     — goto, waitForReady, dialog handling
├── FacebookSession.ts        — is this profile logged in? whoami? session guards
├── selectors/
│   ├── authentication.selectors.ts
│   ├── navigation.selectors.ts
│   ├── composer.selectors.ts
│   └── messaging.selectors.ts
├── actions/
│   ├── createPost.ts
│   ├── uploadMedia.ts
│   ├── comment.ts
│   ├── reactToPost.ts
│   └── sendMessage.ts
└── errors/
```

`FacebookAutomation` dispatches; it does not contain step logic. Each action is
its own module with a single exported function, which keeps every file small and
makes an action reviewable on its own.

## Selectors

Every reference to somebody else's markup lives under `selectors/`. Facebook
changes its DOM often, and a selector scattered through action code turns that
into an archaeology exercise.

Preference order:

1. `getByRole`, `getByLabel`, `getByPlaceholder` — semantic and resilient.
2. `aria-label` / `data-testid` attributes.
3. A structural CSS selector, with a comment saying what it anchors to.

Generated class names are never used.

## Errors and retries

Automation failures are `AppError` subclasses with a `retryable` flag:

| Error                    | Retryable | Why                                                           |
| ------------------------ | --------- | ------------------------------------------------------------- |
| `AutomationTimeoutError` | yes       | A slow page usually loads on the next attempt.                |
| `BrowserCrashedError`    | yes       | A fresh browser may well succeed.                             |
| `SelectorMissingError`   | yes       | Often a not-yet-rendered element.                             |
| `NotLoggedInError`       | no        | A person must sign in inside the profile first.               |
| `AutomationBlockedError` | no        | Facebook refused the action; repeating it makes things worse. |

Unknown throws are classified retryable, because a crashed browser is far more
common than a genuinely impossible action. Retries use exponential backoff with
jitter, bounded by `maxRetries` on the job.

## Pacing

Between steps the engine waits a uniformly random interval between
`minActionDelayMs` and `maxActionDelayMs`. Machine-perfect timing is both
detectable and needlessly harsh on the target site.
