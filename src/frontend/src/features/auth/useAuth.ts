import { useCallback, useEffect, useRef, useState } from 'react';
import {
  API_BASE_URL,
  ApiRequestError,
  SESSION_LOST_EVENT,
  apiJson,
  isAuthErrorCode,
  type AuthErrorCode,
} from '../../lib/api';
import { claimChatStorage, clearChatStorage } from '../../lib/chatStorage';
import { fetchGuestMode, guestStartErrorOf, startGuestSession, type GuestMode } from './guest';
import {
  NO_SESSION_ERRORS,
  clearRedirectMark,
  getSessionStorage,
  loginUrl,
  markRedirect,
  readLastRedirect,
  shouldAutoRedirect,
  visibleLoginError,
  type LoginError,
  type LoginOptions,
} from './redirect';

export interface AuthUser {
  id: string;
  email: string | null;
  username: string | null;
  name: string | null;
  // in the admin group (OIDC_ADMIN_GROUP); the admin API checks it again
  is_admin: boolean;
  // guest trial without an account (limited questions, no USOS)
  is_guest: boolean;
}

// `guest` = the trial offered on the login screen (null = not offered)
type AuthState =
  | { status: 'loading' }
  | { status: 'authenticated'; user: AuthUser }
  | { status: 'unauthenticated'; error: LoginError | null; guest: GuestMode | null };

type ResolvedAuthState = Exclude<AuthState, { status: 'loading' }>;

interface LogoutResponse {
  logout_url: string | null;
}

// ?auth_error=... is added by the backend after a failed login - read it once
// and remove it from the address bar.
function takeAuthErrorFromUrl(): AuthErrorCode | null {
  const url = new URL(window.location.href);
  const code = url.searchParams.get('auth_error');
  if (code === null) return null;
  url.searchParams.delete('auth_error');
  window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  return isAuthErrorCode(code) ? code : 'login_failed';
}

// Read once per page load: StrictMode runs effects twice in dev, and the first
// run strips the param from the URL - the second must still see the error.
let urlErrorCache: AuthErrorCode | null | undefined;
function authErrorFromUrlOnce(): AuthErrorCode | null {
  if (urlErrorCache === undefined) urlErrorCache = takeAuthErrorFromUrl();
  return urlErrorCache;
}

// Set once navigation to Keycloak has started. Later 401s from requests still
// in flight must not flip the page to an error screen (the guard would see a
// fresh mark and report "login did not complete").
let redirecting = false;

async function fetchCurrentUser(): Promise<ResolvedAuthState> {
  try {
    const user = await apiJson<AuthUser>('/auth/me');
    // an older backend does not send is_guest
    return { status: 'authenticated', user: { ...user, is_guest: user.is_guest === true } };
  } catch (error) {
    if (!(error instanceof ApiRequestError)) {
      return { status: 'unauthenticated', error: 'provider_unavailable', guest: null };
    }
    // no session at startup is the normal state, not an error to show
    if (error.status === 401) return { status: 'unauthenticated', error: visibleLoginError(error.code), guest: null };
    return { status: 'unauthenticated', error: error.code ?? 'provider_unavailable', guest: null };
  }
}

// The login screen with the trial button; "no session" itself is not an error.
function guestLoginScreen(error: LoginError | null, guest: GuestMode): ResolvedAuthState {
  return { status: 'unauthenticated', error: NO_SESSION_ERRORS.has(error) ? null : error, guest };
}

// full navigation (not fetch) - the backend redirects on to Keycloak
function goToLogin(language: string, options: LoginOptions = {}): void {
  redirecting = true;
  const storage = getSessionStorage();
  if (storage !== null) markRedirect(storage, Date.now());
  window.location.assign(loginUrl(API_BASE_URL, language, options));
}

// Without a session: go straight to Keycloak (returns null) or, for real errors
// and when the loop guard trips, return the login screen state to show.
function redirectOrShow(error: LoginError | null, language: string): ResolvedAuthState | null {
  if (redirecting) return null;
  const storage = getSessionStorage();
  if (storage === null) {
    // no sessionStorage = no loop guard, so never redirect on our own
    return { status: 'unauthenticated', error: visibleLoginError(error), guest: null };
  }
  if (shouldAutoRedirect(error, readLastRedirect(storage), Date.now())) {
    goToLogin(language);
    return null;
  }
  return { status: 'unauthenticated', error: NO_SESSION_ERRORS.has(error) ? 'login_incomplete' : error, guest: null };
}

// Without a session: with the trial on, the login screen offers it (no
// automatic redirect - the visitor chooses); otherwise as before.
async function resolveNoSession(error: LoginError | null, language: string): Promise<ResolvedAuthState | null> {
  const guest = await fetchGuestMode();
  if (guest !== null && guest.enabled) return guestLoginScreen(error, guest);
  return redirectOrShow(error, language);
}

// Session state from the backend (HttpOnly cookie) plus login and logout.
// `language` is the interface language, passed on to the KSI login page.
export function useAuth(language: string) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });
  // read by redirects started from effects and event listeners
  const languageRef = useRef(language);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);
  // the session-lost event only matters once the chat is open; at startup the
  // initial /auth/me result decides (it may carry ?auth_error= to show)
  const isAuthenticatedRef = useRef(false);

  // a guest whose session ends goes back to the login screen with the trial,
  // not through Keycloak
  const isGuestRef = useRef(false);

  useEffect(() => {
    isAuthenticatedRef.current = state.status === 'authenticated';
    isGuestRef.current = state.status === 'authenticated' && state.user.is_guest;
  }, [state]);

  useEffect(() => {
    let cancelled = false;
    const urlError = authErrorFromUrlOnce();

    void fetchCurrentUser().then((result) => {
      if (cancelled) return;
      if (result.status === 'authenticated') {
        const storage = getSessionStorage();
        if (storage !== null) clearRedirectMark(storage);
        claimChatStorage(result.user.id);
        setState(result);
        return;
      }
      // null = the browser is already on its way to Keycloak, keep the spinner
      void resolveNoSession(urlError ?? result.error, languageRef.current).then((next) => {
        if (!cancelled && next !== null) setState(next);
      });
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // the backend rejected the session mid-use (expired / removed from the group)
  useEffect(() => {
    const onSessionLost = (event: Event) => {
      if (!isAuthenticatedRef.current) return;
      isAuthenticatedRef.current = false;
      const code = (event as CustomEvent<AuthErrorCode>).detail;
      if (code === 'not_member') clearChatStorage();
      if (isGuestRef.current) {
        // the trial session ended (expired or switched off): back to the choice
        clearChatStorage();
        setState({ status: 'loading' });
        void resolveNoSession(null, languageRef.current).then((next) => {
          if (next !== null) setState(next);
        });
        return;
      }
      // expired session: back through Keycloak (usually invisible thanks to SSO)
      setState(redirectOrShow(code, languageRef.current) ?? { status: 'loading' });
    };
    window.addEventListener(SESSION_LOST_EVENT, onSessionLost);
    return () => window.removeEventListener(SESSION_LOST_EVENT, onSessionLost);
  }, []);

  // Back button from the Keycloak page can restore this page from bfcache with
  // the spinner frozen mid-redirect - start over with a fresh load instead.
  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted && redirecting) window.location.reload();
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, []);

  const logout = useCallback(async () => {
    isAuthenticatedRef.current = false;
    clearChatStorage();
    let logoutUrl: string | null = null;
    try {
      logoutUrl = (await apiJson<LogoutResponse>('/auth/logout', { method: 'POST' })).logout_url;
    } catch {
      // the session is unusable in this browser either way
    }
    if (logoutUrl) {
      // also ends the Keycloak session and comes back to the home page
      window.location.assign(logoutUrl);
      return;
    }
    // a guest (no Keycloak session) or a failed logout: the login screen
    const guest = await fetchGuestMode();
    setState({ status: 'unauthenticated', error: null, guest: guest !== null && guest.enabled ? guest : null });
  }, []);

  const login = useCallback((options: LoginOptions = {}) => goToLogin(languageRef.current, options), []);

  // "Continue without an account" on the login screen
  const startGuest = useCallback(async () => {
    const shown = state.status === 'unauthenticated' ? state.guest : null;
    try {
      await startGuestSession();
    } catch (error) {
      setState({ status: 'unauthenticated', error: guestStartErrorOf(error), guest: shown });
      return;
    }
    const result = await fetchCurrentUser();
    if (result.status === 'authenticated') {
      claimChatStorage(result.user.id);
      setState(result);
      return;
    }
    setState({ status: 'unauthenticated', error: result.error ?? 'guest_failed', guest: shown });
  }, [state]);

  // A guest who wants the full chat: end the trial (its conversations go
  // with it) and log in with KSI.
  const loginFromGuest = useCallback(async () => {
    isAuthenticatedRef.current = false;
    clearChatStorage();
    try {
      await apiJson<LogoutResponse>('/auth/logout', { method: 'POST' });
    } catch {
      // the new login replaces the cookie either way
    }
    goToLogin(languageRef.current);
  }, []);

  return { state, login, logout, startGuest, loginFromGuest };
}
