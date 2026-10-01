import type { AuthErrorCode } from '../../lib/api';

// Automatic redirect to KSI login when the visitor has no session.
//
// Only "no session" states redirect on their own. Real errors (not a member,
// login cancelled, Keycloak down...) are shown instead: Keycloak SSO sends the
// browser straight back, so redirecting on them would loop forever.

// Backend codes plus one frontend-only case: an automatic redirect already
// happened moments ago and still produced no session (e.g. blocked cookies).
export type LoginError = AuthErrorCode | 'login_incomplete';

export const AUTO_REDIRECT_GUARD_KEY = 'authAutoRedirectAt';

// A second automatic redirect within this window means the previous one did not
// produce a session (e.g. cookies blocked) - stop and show the login screen.
export const AUTO_REDIRECT_COOLDOWN_MS = 60_000;

// "No session" states - the only ones that redirect on their own.
export const NO_SESSION_ERRORS: ReadonlySet<LoginError | null> = new Set<LoginError | null>([
  null,
  'not_authenticated',
  'session_expired',
]);

// "Not logged in" is the normal state without a session, not an error to show.
export function visibleLoginError(error: LoginError | null): LoginError | null {
  return error === 'not_authenticated' ? null : error;
}

type ReadableStorage = Pick<Storage, 'getItem'>;
type WritableStorage = Pick<Storage, 'setItem' | 'removeItem'>;

export function shouldAutoRedirect(
  error: LoginError | null,
  lastRedirectAt: number | null,
  now: number,
): boolean {
  if (!NO_SESSION_ERRORS.has(error)) return false;
  if (lastRedirectAt === null || lastRedirectAt > now) return true;
  return now - lastRedirectAt > AUTO_REDIRECT_COOLDOWN_MS;
}

export function readLastRedirect(storage: ReadableStorage): number | null {
  const raw = storage.getItem(AUTO_REDIRECT_GUARD_KEY);
  if (raw === null) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function markRedirect(storage: WritableStorage, now: number): void {
  storage.setItem(AUTO_REDIRECT_GUARD_KEY, String(now));
}

export function clearRedirectMark(storage: WritableStorage): void {
  storage.removeItem(AUTO_REDIRECT_GUARD_KEY);
}

// sessionStorage can throw (privacy modes, disabled storage). Without it the
// loop guard cannot work, so callers must not redirect automatically.
export function getSessionStorage(): Storage | null {
  try {
    const storage = window.sessionStorage;
    storage.getItem(AUTO_REDIRECT_GUARD_KEY);
    return storage;
  } catch {
    return null;
  }
}
