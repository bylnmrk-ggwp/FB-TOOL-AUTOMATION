// Fake data for the throwaway mockup. Shapes mirror what the real app reads:
// roster rows from the Google Sheet (sheet_no, username, facebook_name, the
// linked Brave profile, the sheet-owned STATUS cell: blank / LOGGED IN /
// DISABLED) plus the machine-owned live verdict (loggedIn) and status_reason.

export const ACCOUNTS = [
  { no: 1,  username: 'rene.abalos87',   fbName: 'Rene Abalos',     gmail: 'rene.abalos87@gmail.com',   profile: 'Profile 1 - Rene Abalos',     sheetStatus: 'LOGGED IN', loggedIn: true,  reason: '' },
  { no: 2,  username: 'maricel.dizon',   fbName: 'Maricel Dizon',   gmail: 'maricel.dizon@gmail.com',   profile: 'Profile 2 - Maricel Dizon',   sheetStatus: 'LOGGED IN', loggedIn: true,  reason: '' },
  { no: 3,  username: 'jomar.tenorio',   fbName: 'Jomar Tenorio',   gmail: 'jomar.tenorio@gmail.com',   profile: 'Profile 3 - Jomar Tenorio',   sheetStatus: 'LOGGED IN', loggedIn: true,  reason: '' },
  { no: 4,  username: 'anna.villanueva', fbName: 'Anna Villanueva', gmail: 'anna.villanueva@gmail.com', profile: 'Profile 4 - Anna Villanueva', sheetStatus: 'LOGGED IN', loggedIn: false, reason: 'session expired' },
  { no: 5,  username: 'kristoffer.lim',  fbName: 'Kristoffer Lim',  gmail: 'kristoffer.lim@gmail.com',  profile: 'Profile 5 - Kristoffer Lim',  sheetStatus: '',          loggedIn: false, reason: '' },
  { no: 6,  username: 'jenny.pascual',   fbName: 'Jenny Pascual',   gmail: 'jenny.pascual@gmail.com',   profile: 'Profile 6 - Jenny Pascual',   sheetStatus: '',          loggedIn: false, reason: '' },
  { no: 7,  username: 'carlo.mendoza',   fbName: 'Carlo Mendoza',   gmail: 'carlo.mendoza@gmail.com',   profile: '',                            sheetStatus: '',          loggedIn: false, reason: 'no Brave profile' },
  { no: 8,  username: 'liza.bautista',   fbName: 'Liza Bautista',   gmail: 'liza.bautista@gmail.com',   profile: 'Profile 8 - Liza Bautista',   sheetStatus: 'DISABLED',  loggedIn: false, reason: 'account disabled by Facebook' },
  { no: 9,  username: 'paolo.ramirez',   fbName: 'Paolo Ramirez',   gmail: 'paolo.ramirez@gmail.com',   profile: 'Profile 9 - Paolo Ramirez',   sheetStatus: 'DISABLED',  loggedIn: false, reason: 'checkpoint, ID requested' },
  { no: 10, username: 'sheila.ocampo',   fbName: 'Sheila Ocampo',   gmail: 'sheila.ocampo@gmail.com',   profile: 'Profile 10 - Sheila Ocampo',  sheetStatus: 'LOGGED IN', loggedIn: true,  reason: 'too many shares in 1 h', rateLimited: true },
  { no: 11, username: 'mark.delacruz',   fbName: 'Mark Dela Cruz',  gmail: 'mark.delacruz@gmail.com',   profile: 'Profile 11 - Mark Dela Cruz', sheetStatus: 'LOGGED IN', loggedIn: true,  reason: '' },
  { no: 12, username: 'grace.santos',    fbName: 'Grace Santos',    gmail: 'grace.santos@gmail.com',    profile: 'Profile 12 - Grace Santos',   sheetStatus: 'LOGGED IN', loggedIn: true,  reason: '' },
]

// Same precedence as AccountsPage._row_for in the plan.
export function statusOf(a) {
  if (a.sheetStatus === 'DISABLED') return { kind: 'disabled', text: '✕ Disabled' }
  if (a.sheetStatus === 'LOGGING IN') return { kind: 'running', text: '◌ Logging in…' }
  if (a.rateLimited) return { kind: 'warn', text: '⚠ Rate limited' }
  if (a.loggedIn) return { kind: 'ok', text: '● Logged in' }
  if (a.sheetStatus === '') return { kind: 'pending', text: '○ Pending' }
  return { kind: 'off', text: '○ Not logged in' }
}

// db.count_accounts / logged_in_profiles / count_pending / count_disabled, in one go.
export function counts(accounts) {
  const disabled = accounts.filter(a => a.sheetStatus === 'DISABLED').length
  const loggedIn = accounts.filter(a => a.loggedIn && a.sheetStatus !== 'DISABLED').length
  const pendingRows = accounts.filter(a => a.sheetStatus === '')
  return {
    total: accounts.length,
    loggedIn,
    disabled,
    pending: pendingRows.length,
    pendingUnlinked: pendingRows.filter(a => !a.profile).length,
    pendingUsernames: pendingRows.filter(a => a.profile).map(a => a.username),
  }
}

const POST = 'https://www.facebook.com/mcarsph/posts/'

export const QUEUE_ITEMS = [
  { id: 1, profile: 'Profile 1 - Rene Abalos',     action: 'Share to timeline', url: POST + '1029384756', comment: 'Test drive this weekend!', status: 'pending' },
  { id: 2, profile: 'Profile 2 - Maricel Dizon',   action: 'Share to timeline', url: POST + '1029384756', comment: 'Test drive this weekend!', status: 'pending' },
  { id: 3, profile: 'Profile 3 - Jomar Tenorio',   action: 'React (Love)',      url: POST + '1029384756', comment: '',                         status: 'pending' },
  { id: 4, profile: 'Profile 10 - Sheila Ocampo',  action: 'Share to timeline', url: POST + '1029377710', comment: '',                         status: 'failed' },
  { id: 5, profile: 'Profile 11 - Mark Dela Cruz', action: 'Comment',           url: POST + '1029377710', comment: 'Available in Cebu?',       status: 'done' },
  { id: 6, profile: 'Profile 12 - Grace Santos',   action: 'Share to timeline', url: POST + '1029377710', comment: '',                         status: 'done' },
]

export const GROUPS = [
  { id: 1, name: 'Cebu Car Buy and Sell',          members: '128k', checked: true },
  { id: 2, name: 'Toyota Owners Philippines',      members: '96k',  checked: true },
  { id: 3, name: 'Second Hand Cars Metro Manila',  members: '210k', checked: false },
  { id: 4, name: 'Fortuner Club PH',               members: '41k',  checked: false },
  { id: 5, name: 'Davao Auto Market',              members: '73k',  checked: true },
  { id: 6, name: 'Car Financing Tips Philippines', members: '18k',  checked: false },
]

export const PRESETS = [
  'Vios promo - September',
  'Fortuner 2026 launch',
  'Weekend test drive',
]

export const RECENT_SHARES = [
  { time: '20:11', profile: 'Grace Santos',   target: 'Timeline',                  ok: true },
  { time: '20:10', profile: 'Mark Dela Cruz', target: 'Cebu Car Buy and Sell',     ok: true },
  { time: '20:08', profile: 'Sheila Ocampo',  target: 'Timeline',                  ok: false },
  { time: '19:52', profile: 'Rene Abalos',    target: 'Toyota Owners Philippines', ok: true },
]

export const LOG_LINES = [
  { time: '19:48:02', kind: 'info',  text: 'Sheet synced: 12 rows, 0 changed' },
  { time: '19:52:14', kind: 'ok',    text: '✓ Rene Abalos: shared to Toyota Owners Philippines' },
  { time: '20:08:33', kind: 'error', text: '✗ Sheila Ocampo: share refused, rate limited (too many shares in 1 h)' },
  { time: '20:09:41', kind: 'info',  text: 'Sheet synced: 12 rows, 1 changed (sheila.ocampo STATUS)' },
  { time: '20:10:05', kind: 'ok',    text: '✓ Mark Dela Cruz: shared to Cebu Car Buy and Sell' },
  { time: '20:11:07', kind: 'ok',    text: '✓ Grace Santos: shared to timeline' },
  { time: '20:11:09', kind: 'error', text: '✗ Anna Villanueva: not logged in (session expired)' },
  { time: '20:11:10', kind: 'info',  text: 'Batch finished: 132 ok, 8 failed' },
]

export const PROFILE_MEMORY = [
  { profile: 'Profile 1 - Rene Abalos',     procs: 4, mb: 612 },
  { profile: 'Profile 2 - Maricel Dizon',   procs: 3, mb: 541 },
  { profile: 'Profile 3 - Jomar Tenorio',   procs: 3, mb: 498 },
  { profile: 'Profile 10 - Sheila Ocampo',  procs: 2, mb: 377 },
  { profile: 'Profile 11 - Mark Dela Cruz', procs: 3, mb: 655 },
  { profile: 'Profile 12 - Grace Santos',   procs: 2, mb: 421 },
]

export const SYSTEM = { ramUsedGb: 8.6, ramTotalGb: 17.9, browserGb: 3.2, procs: 17, peakGb: 4.1 }
