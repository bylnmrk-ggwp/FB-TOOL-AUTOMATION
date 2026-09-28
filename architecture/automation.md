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
`AbortSignal` for cancellation, a timeout, the human-like delay range, the
operator's `Settings` (for the anti-spam ranges under Pacing) and an
`askOperator` callback that pauses the job and asks a person. The queue depends
on this interface, so job execution can be tested against a fake gateway with
no browser at all.

## Facebook implementation

```
facebook/
├── FacebookAutomation.ts     — implements AutomationGateway, dispatches on action.type
├── FacebookNavigation.ts     — goto, waitForReady, dialog handling
├── FacebookSession.ts        — is this profile logged in? which gate is it on? captcha handling
├── humanInput.ts             — mouse paths, typing rhythm, the pause after a page opens
├── selectors/
│   ├── authentication.selectors.ts
│   ├── composer.selectors.ts
│   ├── engagement.selectors.ts
│   ├── friends.selectors.ts
│   ├── groups.selectors.ts
│   ├── messaging.selectors.ts
│   ├── navigation.selectors.ts
│   ├── profile.selectors.ts
│   ├── share.selectors.ts
│   └── watch.selectors.ts
└── actions/
    ├── types.ts              — ActionContext, step(), pause(), cancellation helpers
    ├── createPost.ts, uploadMedia.ts, comment.ts, reactToPost.ts, sendMessage.ts
    ├── postPage.ts           — open a post and get back to it
    ├── shareSheet.ts         — open the share sheet, pick an option, press Post, read a refusal
    ├── sharePost.ts, shareToGroup.ts
    ├── groups.ts             — fetchGroups, joinGroup
    ├── login.ts              — login, checkLogin
    ├── friends.ts            — acceptFriendRequests, addFriends
    ├── profile.ts            — autoSetupProfile, readMyProfile
    └── watchLive.ts
```

`FacebookAutomation` dispatches; it does not contain step logic. Each action is
its own module with a single exported function, which keeps every file small and
makes an action reviewable on its own. The login action is the one case where
the dispatcher fetches something first: it asks a `CredentialSource` for the
account's stored username and password, and nothing else ever sees them.

Error classes are not defined here. Every failure an action raises is one of
the `AppError` subclasses in `@fb/shared`, so the queue and the HTTP layer read
the same code and the same retryable flag.

## Human-like input

`locator.fill()` writes a field in one DOM assignment and `locator.click()`
lands the pointer on an element's exact centre. Neither produces what a person
cannot help producing, and anti-bot scoring reads exactly those signals; a poor
score is what puts an "I'm not a robot" box in front of a login. `humanInput.ts`
exists so the automation does not look mechanical while it types a password the
operator owns. It does nothing to defeat a challenge.

- **Mouse.** `moveTo` walks the pointer along a quadratic Bezier curve from
  where it last was to the target, bowed to one side by a random amount, eased
  at both ends, with a pixel or two of jitter on every intermediate point and a
  short random sleep between steps. The number of steps scales with the
  distance.
- **Click.** `humanClick` aims somewhere in the middle third of the element,
  never its exact centre, pauses, then holds the button down for 50–140 ms.
  `clickLike` uses it when the element has a bounding box and falls back to
  Playwright's own click when it does not.
- **Keyboard.** `humanType` clicks into the field and types one character at a
  time, 55–190 ms apart, with a longer beat after `@`, `.`, `_`, `-` and a
  space, and an occasional longer stop somewhere in the string.
- **Reading.** `settle(page)` waits 0.9–2.4 s after a page opens, before
  anything is touched, and six times in ten drifts the cursor once.
- **Fidgeting.** `wander` moves the cursor to one to three places a reader's
  hand might rest, never the same path twice. `scrollAround` scrolls the wheel
  in short bursts of a few notches, mostly down, now and then back up to
  re-read. `idle(page, ms, { signal, scroll })` spends a whole wait that way:
  a stretch of stillness (usually a few seconds, sometimes a long look), then
  a scroll, a drift or nothing at all, with every gap drawn fresh so there is
  no rhythm to pick out. A micro-action that fails because the page moved on
  is dropped silently; idling is never the reason a job fails.

## Gates and the login state

Facebook sends a session it will not let use the account to one of a handful
of URL paths: `/login`, `/checkpoint`, `/twofactor`, `/two_step_verification`,
`/approvals`, `/confirmemail` and `/recover` (`GATE_PATHS` in
`authentication.selectors.ts`). `FacebookSession.isGatedUrl` tests the URL's
path against those prefixes, never a substring of the whole URL, because a
group called "carrecovery" would otherwise read as a recovery gate.

`FacebookSession.classify(page)` turns whatever page the browser is on into an
`AccessVerdict`, a `LoginStatus` plus a reason in words. A live session is
checked first, so an account that failed for some other reason is never
recorded as signed out; after that the body text and URL are read for a
disabled or suspended notice, an email-confirmation page, a two-factor prompt,
a checkpoint, a captcha and finally the login form itself. Every action other
than login starts with `assertUsable`, which opens the home page, classifies
it, and throws `NotLoggedInError` for a plain sign-out or `AccountGatedError`
naming the gate for anything else.

The `login` job signs in with the stored credentials. It checks for an existing
session first, opens `login.php`, clicks past the "Use another profile" chooser
a remembered-but-invalidated session lands on, and types the username and
password with `humanType`. A reCAPTCHA checkbox is ticked by the automation
itself, since a profile with history usually gets its token from that alone; a
picture challenge, a two-factor code or a checkpoint is handed to a person (see
the next section) when the job's `waitForOperator` is true, and otherwise
recorded as the account's login status without waiting. The `check_login` job
types nothing: it opens the home page and records what `classify` says. Both
end by reading the profile name and URL, and the queue writes the verdict onto
the account whether the job succeeded or failed, so the roster stays honest.

## Stopping for a person

`askOperator` on the context is the human-in-the-loop seam. An action that
meets something only a person can clear calls it with a kind (`captcha`,
`two_factor`, `checkpoint`, `confirm` or `text`) and a message. The queue routes
that to `OperatorInputService` in `packages/application`, which publishes an
`input.requested` event, lists the request on `GET /input`, and holds the job
until someone answers on `POST /input`. The browser window stays open the whole
time, so the usual answer is "I did it in the window" rather than typed text.

The wait is bounded by `settings.operatorInputTimeoutMs` (180 000 ms by
default); when it lapses the job fails with `OperatorInputTimeoutError`.
Cancelling the job answers its request as cancelled, and the first answer
settles the request for every open tab. Requests are held in memory only: one a
restart loses belonged to a job the restart failed anyway.

## The share sheet

`share_post` and `share_to_group` go through the same sheet: open the post,
press Share, pick an option, press Post if the full composer opened, wait the
`afterPost` pause, and then check whether the sheet is still open, which means
the share did not land. For a group the option is "Share to a group", after
which the group is searched by name and the first result taken; a name that
finds nothing raises `GroupNotFoundError`. When `shareToTimeline` is set on a
group share, the timeline and story shares happen first, and a story that will
not take is logged and skipped rather than costing the group share.

A share that does not land is tried up to three times, with a wait that grows
each attempt, but only when the refusal is one of Facebook's own "try again"
family ("something went wrong", "please try again", "temporarily unavailable"
and so on). From the second attempt a timeline share is sent through the full
composer instead of "Share now", which is a different server call and has been
accepted seconds after the other was refused. A refusal that names the account
("temporarily blocked", "restricted", "community standards", …) is a
restriction, not a hiccup: repeating it is what gets the account restricted
further, so it raises `ShareRestrictedError`, which is not retryable. The queue
then records a twelve-hour share restriction on the account
(`SHARE_RESTRICTION_HOURS` in `JobProcessor`), and any further `share_post` or
`share_to_group` job for that account is failed up front until the restriction
lapses. Every other job type is unaffected.

When a share does land, the queue records it in `account_activity`, and the
fan-out endpoints read that table to skip it next time.

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

| Error                                                       | Retryable | Why                                                                                             |
| ----------------------------------------------------------- | --------- | ----------------------------------------------------------------------------------------------- |
| `AutomationTimeoutError`                                    | yes       | A slow page usually loads on the next attempt.                                                  |
| `BrowserCrashedError`                                       | yes       | A fresh browser may well succeed.                                                               |
| `SelectorMissingError`                                      | yes       | Often a not-yet-rendered element.                                                               |
| `NotLoggedInError`                                          | no        | A person must sign in inside the profile first.                                                 |
| `AutomationBlockedError`                                    | no        | Facebook refused the action; repeating it makes things worse.                                   |
| `AutomationFailedError`                                     | yes       | A step did not land; the next attempt usually does.                                             |
| `AccountGatedError`                                         | no        | A checkpoint or code prompt; another attempt hits the same wall.                                |
| `LoginFailedError`                                          | no        | Wrong password or a rejected attempt. Retryable only when the login page itself failed to load. |
| `CredentialsMissingError`                                   | no        | No username and password are stored for the account.                                            |
| `ShareRestrictedError`                                      | no        | Facebook named the account; the account is held for twelve hours.                               |
| `GroupNotFoundError`                                        | no        | The group search found nothing by that name.                                                    |
| `OperatorInputTimeoutError` / `OperatorInputCancelledError` | no        | Nobody answered in time, or the person gave up.                                                 |

Unknown throws are classified retryable, because a crashed browser is far more
common than a genuinely impossible action. Retries use exponential backoff with
jitter, bounded by `maxRetries` on the job.

## Pacing

Between steps the engine waits a uniformly random interval between
`minActionDelayMs` and `maxActionDelayMs`. Machine-perfect timing is both
detectable and needlessly harsh on the target site.

The share and group actions also wait at the moments a person would, drawn from
the ranges the operator sets on the Settings page (`DELAY_RANGES` in
`packages/shared/src/schemas/settings.ts`). An action asks for one by name
through `pause(context, name)` in `actions/types.ts`, which reads the range off
`AutomationContext.settings`. A wait under three seconds is a plain sleep in
short slices, so a cancellation cuts it short instead of waiting it out. A wait
of three seconds or more is logged and handed to `idle()`, so the browser is
not frozen for the duration: the cursor drifts and the page scrolls a little at
irregular, freshly drawn moments. Scrolling is withheld for the
`afterShareButton` and `step` delays, because a dialog may be holding the page.

| Name               | Default   | Taken                                                                                                                                                                                        |
| ------------------ | --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `step`             | 0.8–2.5 s | Between steps; the same range as `minActionDelayMs`/`maxActionDelayMs`                                                                                                                       |
| `afterShareButton` | 2–5 s     | After the Share button opens the sheet, before an option is picked                                                                                                                           |
| `afterPost`        | 8–15 s    | After Post is pressed, for the share to land before anything else moves                                                                                                                      |
| `afterComment`     | 3–5 s     | After a comment is posted                                                                                                                                                                    |
| `betweenJoins`     | 3–5 s     | After a group join                                                                                                                                                                           |
| `betweenShares`    | 15–45 s   | At the end of every `share_to_group` job ("Lingering before the next share"), so consecutive group shares for one account are spaced inside the job, while nothing else runs on that account |

`watch_live` idles the same way between its checks that the video is still
playing, for a random 15–50 s each time, with scrolling off so the player stays
in view.

Setting a range to zero is possible and unwise. A minimum above its maximum is
rejected by the settings endpoint.
