// Display helpers for the admin panel. Pure functions, locale passed in.

export const EMPTY = '—';

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;
const BYTES_PER_UNIT = 1024;
const MS_PER_SECOND = 1000;

// Binary units (1 KB = 1024 B), at most one decimal.
export function formatBytes(bytes: number, locale: string): string {
  let value = bytes;
  let unit = 0;
  while (value >= BYTES_PER_UNIT && unit < BYTE_UNITS.length - 1) {
    value /= BYTES_PER_UNIT;
    unit += 1;
  }
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: unit === 0 ? 0 : 1 }).format(value);
  return `${number} ${BYTE_UNITS[unit]}`;
}

const DURATION_UNITS: readonly (readonly [string, number])[] = [
  ['d', 86400],
  ['h', 3600],
  ['min', 60],
  ['s', 1],
];

// Uptime like "2 h 15 min": the two largest non-zero units.
export function formatDuration(totalSeconds: number): string {
  let rest = Math.max(0, Math.floor(totalSeconds));
  const parts: string[] = [];
  for (const [label, size] of DURATION_UNITS) {
    const amount = Math.floor(rest / size);
    rest -= amount * size;
    if (amount > 0 || (parts.length === 0 && size === 1)) parts.push(`${amount} ${label}`);
    if (parts.length === 2) break;
  }
  return parts.join(' ');
}

export function formatLatency(ms: number | null, locale: string): string {
  if (ms === null) return EMPTY;
  if (ms < MS_PER_SECOND) return `${Math.round(ms)} ms`;
  const seconds = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(ms / MS_PER_SECOND);
  return `${seconds} s`;
}

export function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value);
}

// `timeZone` is for tests; the browser's zone is used by default.
export function formatDateTime(iso: string | null, locale: string, timeZone?: string): string {
  if (iso === null) return EMPTY;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone }).format(date);
}

export interface PersonFields {
  name: string | null;
  username: string | null;
  email: string | null;
}

export function personLabel(person: PersonFields): string {
  return person.name || person.username || person.email || '';
}

// "3 / 10" or "3 / ∞" (no limit).
export function usageLabel(used: number, limit: number | null): string {
  return `${used} / ${limit === null ? '∞' : limit}`;
}
