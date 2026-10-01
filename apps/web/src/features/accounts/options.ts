import { ACCOUNT_STATUSES, LOGIN_STATUSES } from '@fb/shared';
import { LOGIN_LABELS } from '@/components/common/StatusDot';

/** Filter choices every account list shares; the empty value means "any". */
export const STATUS_OPTIONS = [
  { value: '', label: 'Any browser state' },
  ...ACCOUNT_STATUSES.map((status) => ({ value: status, label: status })),
];

export const LOGIN_OPTIONS = [
  { value: '', label: 'Any login state' },
  ...LOGIN_STATUSES.map((status) => ({ value: status, label: LOGIN_LABELS[status] })),
];
