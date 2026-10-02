import { ApiRequestError, apiJson } from '../../lib/api';
import { parseAttachmentLimits, type AttachmentLimits } from './attachments';

// Daily question limit and the admins' chat switch: GET /usage, the 429
// "rate_limited" and the 503 "chat_disabled" answers of POST /chat/stream.
// The day ends at midnight Polish time (server side).

export interface UsageStatus {
  used: number;
  // null = no limit (an exception granted by the admins)
  limit: number | null;
  // ISO time of the next reset
  resetAt: string;
  // false = the admins switched the chat off for everyone
  chatEnabled: boolean;
  // the admins' own text for the banner (null = translated default)
  chatDisabledMessage: string | null;
  // attachment limits for the input (missing = older backend, no paperclip)
  attachments?: AttachmentLimits;
}

// What a 503 chat_disabled tells: the admins' message, if they wrote one.
export interface ChatDisabledInfo {
  adminMessage: string | null;
}

// What a 429 tells about the exhausted limit.
export interface RateLimitInfo {
  limit: number;
  resetAt: string;
}

const RATE_LIMITED = 'rate_limited';
const CHAT_DISABLED = 'chat_disabled';
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
  const { used, limit, reset_at: resetAt, chat_enabled: enabled, chat_disabled_message: message } = value;
  if (!isCount(used) || !(limit === null || isCount(limit)) || !isIsoDate(resetAt)) return null;
  const attachments = parseAttachmentLimits(value.attachments);
  return {
    used,
    limit,
    resetAt,
    // a backend without the switch never disables the chat
    chatEnabled: enabled !== false,
    chatDisabledMessage: typeof message === 'string' && message !== '' ? message : null,
    ...(attachments !== null ? { attachments } : {}),
  };
}

// The chat switch info of a 503 chat_disabled error, or null for any other error
// (a 503 from the login server is something else).
export function parseChatDisabled(error: unknown): ChatDisabledInfo | null {
  if (!(error instanceof ApiRequestError) || error.status !== 503) return null;
  const { detail } = error;
  if (!isRecord(detail) || detail.code !== CHAT_DISABLED) return null;
  const message = detail.admin_message;
  return { adminMessage: typeof message === 'string' && message !== '' ? message : null };
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
// `attachments` (the last known attachment limits) are kept as they were.
export function exhaustedUsage(info: RateLimitInfo, attachments?: AttachmentLimits): UsageStatus {
  // a 429 means the chat itself is on
  return {
    used: info.limit,
    limit: info.limit,
    resetAt: info.resetAt,
    chatEnabled: true,
    chatDisabledMessage: null,
    ...(attachments !== undefined ? { attachments } : {}),
  };
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
