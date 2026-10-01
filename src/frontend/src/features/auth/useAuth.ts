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
} from './redirect';

export interface AuthUser {
  id: string;
  email: string | null;
  username: string | null;
  name: string | null;
}

type AuthState =
  | { status: 'loading' }
  | { status: 'authenticated'; user: AuthUser }
  | { status: 'unauthenticated'; error: LoginError | null };

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
    return { status: 'authenticated', user };
  } catch (error) {
    if (!(error instanceof ApiRequestError)) return { status: 'unauthenticated', error: 'provider_unavailable' };
    // no session at startup is the normal state, not an error to show
    if (error.status === 401) return { status: 'unauthenticated', error: visibleLoginError(error.code) };
    return { status: 'unauthenticated', error: error.code ?? 'provider_unavailable' };
  }
}

// full navigation (not fetch) - the backend redirects on to Keycloak
function goToLogin(language: string): void {
  redirecting = true;
  const storage = getSessionStorage();
  if (storage !== null) markRedirect(storage, Date.now());
  window.location.assign(loginUrl(API_BASE_URL, language));
}

// Without a session: go straight to Keycloak (returns null) or, for real errors
// and when the loop guard trips, return the login screen state to show.
function redirectOrShow(error: LoginError | null, language: string): ResolvedAuthState | null {
  if (redirecting) return null;
  const storage = getSessionStorage();
  if (storage === null) {
    // no sessionStorage = no loop guard, so never redirect on our own
    return { status: 'unauthenticated', error: visibleLoginError(error) };
  }
  if (shouldAutoRedirect(error, readLastRedirect(storage), Date.now())) {
    goToLogin(language);
    return null;
  }
  return { status: 'unauthenticated', error: NO_SESSION_ERRORS.has(error) ? 'login_incomplete' : error };
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

  useEffect(() => {
    isAuthenticatedRef.current = state.status === 'authenticated';
  }, [state.status]);

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
      const next = redirectOrShow(urlError ?? result.error, languageRef.current);
      if (next !== null) setState(next);
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
    setState({ status: 'unauthenticated', error: null });
  }, []);

  const login = useCallback(() => goToLogin(languageRef.current), []);

  return { state, login, logout };
}
