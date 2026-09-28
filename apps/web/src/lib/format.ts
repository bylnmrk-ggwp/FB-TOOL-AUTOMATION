const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
const TIME = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});
const DATE_TIME = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' });

/** "3 minutes ago" for anything recent, an absolute date once it is old. */
export const relativeTime = (iso: string): string => {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';

  const seconds = Math.round((then - Date.now()) / 1000);
  const absolute = Math.abs(seconds);

  if (absolute < 60) return RELATIVE.format(seconds, 'second');
  if (absolute < 3_600) return RELATIVE.format(Math.round(seconds / 60), 'minute');
  if (absolute < 86_400) return RELATIVE.format(Math.round(seconds / 3_600), 'hour');
  if (absolute < 604_800) return RELATIVE.format(Math.round(seconds / 86_400), 'day');
  return DATE_TIME.format(then);
};

export const clockTime = (iso: string): string => {
  const value = new Date(iso);
  return Number.isNaN(value.getTime()) ? '—' : TIME.format(value);
};

export const dateTime = (iso: string | null): string => {
  if (iso === null) return '—';
  const value = new Date(iso);
  return Number.isNaN(value.getTime()) ? '—' : DATE_TIME.format(value);
};

export const duration = (ms: number): string => {
  if (ms < 1_000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
};

export const bytes = (value: number): string => {
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
};

/** `create_post` reads as "Create post" in the UI. */
export const humanise = (value: string): string => {
  const spaced = value.replace(/[_.]/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
};
