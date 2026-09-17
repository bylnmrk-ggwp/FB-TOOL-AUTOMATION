"""Proof: the frontend store speaks the phase-2 routes. Run by verify.py
with globals failures, step and ROOT.

The pages are written against `actions.<name>` and against three new
initialState fields, so a renamed action or a path that does not match
routes/queue.py, compose.py or groups.py breaks a button with no error
anywhere. Two layers check that here:

1. A source scan that always runs, so a machine without node still fails
   when an action or a route path is gone.
2. The store actually imported into node with `fetch` stubbed, which is the
   only way to prove what each action posts, that a 409 becomes a toast
   rather than a silent no-op, and that an unchanged queue keeps its array
   identity (useStore re-renders on every state event otherwise).

Nothing here starts a browser, a server or the worker: node runs one
module with a fake fetch and exits.
"""
import json
import shutil
import subprocess
import sys
sys.path.insert(0, str(ROOT))

step("web store: phase-2 actions")

_WEB = ROOT / "web"
_STORE = _WEB / "src" / "store.js"
_WS = _WEB / "src" / "ws.js"

# The names the Queue and Compose pages call. A rename here is a rename in
# two page files that nothing else would catch.
_ACTIONS = (
    "queueAdd", "queueRemove", "queueClear", "queueRun", "queueWatch",
    "queueStopWatch", "refreshGroups", "fetchGroups", "composeShare",
    "composeShareTimeline", "composeShareGroups", "composeShareBulk",
    "composeJoin", "composePostTimeline", "uploadImage",
)

# Every path phase 2 added, as the route modules spell it.
_PATHS = (
    "/api/queue/add", "/api/queue/remove", "/api/queue/clear", "/api/queue/run",
    "/api/queue/watch", "/api/queue/stop-watch", "/api/groups", "/api/groups/fetch",
    "/api/compose/share", "/api/compose/share-timeline", "/api/compose/share-groups",
    "/api/compose/share-bulk", "/api/compose/join", "/api/compose/post-timeline",
    "/api/uploads",
)

_src = _STORE.read_text(encoding="utf-8")
for _name in _ACTIONS:
    if f"{_name}(" not in _src:
        failures.append(f"store.js: action {_name} missing")
for _path in _PATHS:
    if f"'{_path}'" not in _src and f'"{_path}"' not in _src:
        failures.append(f"store.js: nothing posts to {_path}")
for _field in ("queue:", "groups:", "groupsLoading:"):
    if _field not in _src:
        failures.append(f"store.js: initialState.{_field.rstrip(':')} missing")

# The refetch after a groups fetch belongs in ws.js, next to the accounts
# one: reduce stays pure, so the store alone cannot ask for the new rows.
_ws_src = _WS.read_text(encoding="utf-8")
for _rtype in ("fetch_groups_result", "fetch_groups_bulk_result"):
    if _rtype not in _ws_src:
        failures.append(f"ws.js: {_rtype} does not trigger a refetch")
if "refreshGroups" not in _ws_src:
    failures.append("ws.js: never calls actions.refreshGroups")

print(f"source scan: {len(_ACTIONS)} actions, {len(_PATHS)} paths")

# ── The store, run ────────────────────────────────────

# One module, imported with fetch replaced. `-e` rather than a temp file so
# the proof writes nothing: node resolves './src/store.js' and the bare
# 'react' import against cwd, which is web/.
_SCRIPT = r"""
import { initialState, reduce, actions, getState } from './src/store.js'

const fails = []
const ok = (cond, msg) => { if (!cond) fails.push(msg) }

// --- initialState -----------------------------------------------------
ok(Array.isArray(initialState.queue) && initialState.queue.length === 0,
   'initialState.queue must be an empty array')
ok(Array.isArray(initialState.groups) && initialState.groups.length === 0,
   'initialState.groups must be an empty array')
ok(initialState.groupsLoading === false, 'initialState.groupsLoading must be false')

// --- the state event carries the queue --------------------------------
const items = [{ id: 'q1', profile_name: 'P1', action_type: 'group',
                 post_url: 'http://example.com/p', group_name: 'G' }]
const ev = { type: 'state', run: null, last_run_summary: '', queue: items,
             pending_input: null, login_run_active: false, scan_active: false,
             sheet_last_ok: 0, system: {}, bridge_alive: true, version: 'dev',
             counts: { total: 1 } }
const s1 = reduce(initialState, ev)
ok(s1.queue.length === 1 && s1.queue[0].id === 'q1',
   'reduce(state) must copy the server queue into st.queue')
ok(s1.server.queue === undefined,
   'st.server must not keep a second copy of the queue')
const s2 = reduce(s1, { ...ev, queue: items.map(i => ({ ...i })) })
ok(s2.queue === s1.queue,
   'an unchanged queue must come back as the same array')
ok(reduce(s2, { ...ev, queue: [] }).queue.length === 0,
   'an emptied queue must reach the store')
const { queue: _dropped, ...noQueue } = ev
ok(reduce(s1, noQueue).queue === s1.queue,
   'a state event without a queue key must leave the list alone')

// --- what each action posts -------------------------------------------
const calls = []
let next = { status: 202, body: { accepted: true } }
globalThis.fetch = async (path, init = {}) => {
  calls.push({ path, method: init.method || 'GET', body: init.body })
  return new Response(JSON.stringify(next.body), {
    status: next.status, headers: { 'content-type': 'application/json' } })
}
const last = () => calls[calls.length - 1]
const sent = () => JSON.parse(last().body)

async function posts(label, run, path, check) {
  const before = calls.length
  await run()
  if (calls.length === before) { fails.push(label + ' posted nothing'); return }
  if (last().path !== path) { fails.push(label + ' posted to ' + last().path + ', not ' + path); return }
  if (last().method !== 'POST') { fails.push(label + ' used ' + last().method); return }
  let body
  try { body = sent() } catch { fails.push(label + ' sent no JSON body'); return }
  if (!check(body)) fails.push(label + ' body wrong: ' + last().body)
}

await posts('queueAdd', () => actions.queueAdd({
  profile_names: ['P1', 'P2'], action_type: 'group', post_url: 'http://example.com/p',
  group_name: 'G', comment_text: 'hi', reaction: 'like' }),
  '/api/queue/add',
  b => b.profile_names.join(',') === 'P1,P2' && b.action_type === 'group'
       && b.post_url === 'http://example.com/p' && b.group_name === 'G'
       && b.comment_text === 'hi' && b.reaction === 'like')

await posts('queueRemove', () => actions.queueRemove('q7'),
            '/api/queue/remove', b => b.id === 'q7')
await posts('queueClear', () => actions.queueClear(), '/api/queue/clear', () => true)
await posts('queueRun', () => actions.queueRun(), '/api/queue/run', () => true)
await posts('queueWatch', () => actions.queueWatch({
  url: 'http://example.com/w', minutes: 5, profile_names: ['P1'] }),
  '/api/queue/watch',
  b => b.url === 'http://example.com/w' && b.minutes === 5 && b.profile_names[0] === 'P1')
await posts('queueStopWatch', () => actions.queueStopWatch(),
            '/api/queue/stop-watch', () => true)

await posts('fetchGroups', () => actions.fetchGroups(['P1']),
            '/api/groups/fetch', b => b.profile_names[0] === 'P1')
await posts('fetchGroups(all)', () => actions.fetchGroups(),
            '/api/groups/fetch', b => b.profile_names === null)

await posts('composeShare', () => actions.composeShare({
  post_url: 'http://example.com/p', group_name: 'G', comment_text: 'c', reaction: 'love' }),
  '/api/compose/share',
  b => b.post_url === 'http://example.com/p' && b.group_name === 'G'
       && b.comment_text === 'c' && b.reaction === 'love')
await posts('composeShareTimeline', () => actions.composeShareTimeline({
  post_url: 'http://example.com/p' }),
  '/api/compose/share-timeline', b => b.post_url === 'http://example.com/p')
await posts('composeShareGroups', () => actions.composeShareGroups({
  post_url: 'http://example.com/p', groups: [{ name: 'G' }] }),
  '/api/compose/share-groups',
  b => Array.isArray(b.groups) && b.groups[0].name === 'G')
await posts('composeShareBulk', () => actions.composeShareBulk({
  post_url: 'http://example.com/p',
  groups: [{ name: 'G', url: 'http://example.com/g', profiles: ['P1'] }],
  profile_names: ['P1'] }),
  '/api/compose/share-bulk',
  b => b.groups[0].url === 'http://example.com/g' && b.groups[0].profiles[0] === 'P1'
       && b.profile_names[0] === 'P1')
await posts('composeJoin', () => actions.composeJoin({
  urls: ['http://example.com/g'], profile_names: ['P1'] }),
  '/api/compose/join',
  b => b.urls[0] === 'http://example.com/g' && b.profile_names[0] === 'P1')
await posts('composePostTimeline', () => actions.composePostTimeline({
  text: 'hello', image_paths: ['C:/up/a.png'] }),
  '/api/compose/post-timeline',
  b => b.text === 'hello' && b.image_paths[0] === 'C:/up/a.png')

// --- a refusal is a toast, never silence ------------------------------
next = { status: 409, body: { error: 'a run is active' } }
const toastsBefore = getState().toasts.length
const accepted = await actions.queueRun()
ok(accepted === false, 'a refused command must answer false')
const toasts = getState().toasts
ok(toasts.length === toastsBefore + 1, 'a 409 must add one toast')
ok(toasts.length && toasts[toasts.length - 1].text === 'a run is active',
   'the toast must carry the server error')

// --- reads ------------------------------------------------------------
next = { status: 200, body: { groups: [{ name: 'G', url: 'http://example.com/g',
                                         profiles: ['P1'] }] } }
await actions.refreshGroups()
ok(last().path === '/api/groups' && last().method === 'GET',
   'refreshGroups must GET /api/groups')
ok(getState().groups.length === 1 && getState().groups[0].name === 'G',
   'refreshGroups must store the rows')
ok(getState().groupsLoading === false, 'groupsLoading must fall back to false')

// A groups fetch that fails must not leave the spinner on for good.
next = { status: 500, body: { error: 'boom' } }
await actions.refreshGroups()
ok(getState().groupsLoading === false, 'groupsLoading must clear after a failure')

// --- uploads ----------------------------------------------------------
next = { status: 200, body: { path: 'C:/up/a.png', name: 'a.png' } }
const saved = await actions.uploadImage(new File(['x'], 'a.png', { type: 'image/png' }))
ok(last().path === '/api/uploads' && last().method === 'POST',
   'uploadImage must POST /api/uploads')
ok(last().body instanceof FormData, 'uploadImage must send multipart form data')
ok(saved && saved.path === 'C:/up/a.png' && saved.name === 'a.png',
   'uploadImage must answer the route path and name')
next = { status: 400, body: { error: 'that file type is not an image' } }
let threw = null
try { await actions.uploadImage(new File(['x'], 'a.exe')) } catch (e) { threw = e }
ok(threw && threw.error === 'that file type is not an image',
   'a refused upload must throw the server error')

console.log(JSON.stringify({ fails, checks: calls.length }))
"""

_node = shutil.which("node")
if _node is None:
    print("SKIP: node not installed (source scan only)")
elif not (_WEB / "node_modules" / "react" / "package.json").exists():
    print("SKIP: web/node_modules not installed (source scan only)")
else:
    try:
        _proc = subprocess.run([_node, "--input-type=module", "-e", _SCRIPT],
                               cwd=_WEB, timeout=120, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
        _out = _proc.stdout.decode("utf-8", errors="replace").strip()
        _line = _out.splitlines()[-1] if _out else ""
        try:
            _report = json.loads(_line)
        except ValueError:
            failures.append("store.js: node could not run the store")
            for _l in _out.splitlines()[-15:]:
                print("  " + _l.encode("ascii", errors="replace").decode("ascii"))
            _report = None
        if _report is not None:
            for _f in _report["fails"]:
                failures.append(f"store.js: {_f}")
            print(f"store imported, {_report['checks']} request(s) recorded, "
                  f"{len(_report['fails'])} failure(s)")
    except (subprocess.TimeoutExpired, OSError) as _e:
        failures.append(f"store.js: node run failed: {_e}")

print("FAILED" if [f for f in failures if f.startswith(("store.js", "ws.js"))] else "ok")
