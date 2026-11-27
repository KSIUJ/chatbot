import { ApiRequestError, apiJson, isAuthErrorCode } from '../../lib/api';
import type { LoginError } from './redirect';

// Guest trial ("continue without an account"): GET /auth/guest says whether
// the login screen offers it, POST /auth/guest starts a guest session (an
// HttpOnly cookie, no Keycloak). The backend limits the guest's questions.

export interface GuestMode {
  enabled: boolean;
  // questions per guest session
  questionLimit: number;
}

// Errors of POST /auth/guest shown on the login screen.
export type GuestStartError = 'guest_quota' | 'guest_disabled' | 'guest_failed';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

// Server data is not trusted: anything malformed gives null (no guest button).
export function parseGuestMode(value: unknown): GuestMode | null {
  if (!isRecord(value)) return null;
  const { enabled, question_limit: limit } = value;
  if (typeof enabled !== 'boolean') return null;
  if (typeof limit !== 'number' || !Number.isInteger(limit) || limit < 1) return null;
  return { enabled, questionLimit: limit };
}

// What to show after a failed POST /auth/guest. A 429 without the backend's
// JSON comes from the nginx rate limit - the same message as the quota.
export function guestStartErrorOf(error: unknown): LoginError {
  if (!(error instanceof ApiRequestError)) return 'guest_failed';
  if (error.code !== null && isAuthErrorCode(error.code)) return error.code;
  const code = isRecord(error.detail) ? error.detail.code : null;
  if (code === 'guest_disabled') return 'guest_disabled';
  if (error.status === 429) return 'guest_quota';
  return 'guest_failed';
}

// null when the backend is older or unreachable: the login works as before.
export async function fetchGuestMode(): Promise<GuestMode | null> {
  try {
    return parseGuestMode(await apiJson<unknown>('/auth/guest'));
  } catch {
    return null;
  }
}

export async function startGuestSession(): Promise<void> {
  await apiJson<unknown>('/auth/guest', { method: 'POST' });
}
