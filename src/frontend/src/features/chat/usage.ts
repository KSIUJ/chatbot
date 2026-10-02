import { ApiRequestError, apiJson } from '../../lib/api';

// Daily question limit: GET /usage and the 429 "rate_limited" answer of
// POST /chat/stream. The day ends at midnight Polish time (server side).

export interface UsageStatus {
  used: number;
  // null = no limit (an exception granted by the admins)
  limit: number | null;
  // ISO time of the next reset
  resetAt: string;
}

// What a 429 tells about the exhausted limit.
export interface RateLimitInfo {
  limit: number;
  resetAt: string;
}

const RATE_LIMITED = 'rate_limited';
const MS_PER_SECOND = 1000;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value));
}

// Server data is not trusted: anything malformed gives null (no hint shown).
export function parseUsage(value: unknown): UsageStatus | null {
  if (!isRecord(value)) return null;
  const { used, limit, reset_at: resetAt } = value;
  if (!isCount(used) || !(limit === null || isCount(limit)) || !isIsoDate(resetAt)) return null;
  return { used, limit, resetAt };
}

// Reset time from the body, or now + Retry-After (seconds) when it is missing.
function resetTimeOf(detail: Record<string, unknown>, retryAfter: string | null, now: Date): string | null {
  if (isIsoDate(detail.reset_at)) return detail.reset_at;
  if (retryAfter === null || !/^\d+$/.test(retryAfter.trim())) return null;
  return new Date(now.getTime() + Number(retryAfter) * MS_PER_SECOND).toISOString();
}

// The daily limit info of a 429 rate_limited error, or null for any other error.
export function parseRateLimit(error: unknown, now: Date = new Date()): RateLimitInfo | null {
  if (!(error instanceof ApiRequestError) || error.status !== 429) return null;
  const { detail } = error;
  if (!isRecord(detail) || detail.code !== RATE_LIMITED || !isCount(detail.limit)) return null;
  const resetAt = resetTimeOf(detail, error.retryAfter, now);
  return resetAt === null ? null : { limit: detail.limit, resetAt };
}

// Usage right after a 429: the whole limit is used up until the reset.
export function exhaustedUsage(info: RateLimitInfo): UsageStatus {
  return { used: info.limit, limit: info.limit, resetAt: info.resetAt };
}

// When the limit resets, in the interface language: just the time when it is
// within a day (the usual case - next midnight), otherwise date and time.
// `timeZone` is for tests; the browser's zone is used by default.
export function formatResetTime(resetAt: string, locale: string, now: Date = new Date(), timeZone?: string): string {
  const reset = new Date(resetAt);
  if (Number.isNaN(reset.getTime())) return '';
  const withinDay = reset.getTime() - now.getTime() <= MS_PER_DAY;
  const options: Intl.DateTimeFormatOptions = withinDay
    ? { hour: '2-digit', minute: '2-digit', timeZone }
    : { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone };
  return new Intl.DateTimeFormat(locale, options).format(reset);
}

// null when the server sent something unexpected (the hint is just hidden).
export async function fetchUsage(): Promise<UsageStatus | null> {
  return parseUsage(await apiJson<unknown>('/usage'));
}
