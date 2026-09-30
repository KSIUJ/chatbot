import { useCallback, useEffect, useState } from 'react';
import {
  API_BASE_URL,
  SESSION_LOST_EVENT,
  apiFetch,
  isAuthErrorCode,
  readAuthErrorCode,
  type AuthErrorCode,
} from '../../lib/api';
import { claimChatStorage, clearChatStorage } from '../../lib/chatStorage';
import {
  NO_SESSION_ERRORS,
  clearRedirectMark,
  getSessionStorage,
  markRedirect,
  readLastRedirect,
  shouldAutoRedirect,
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

interface LogoutResponse {
  logout_url: string | null;
}

// ?auth_error=... dopisywane przez backend po nieudanym logowaniu -
// odczytujemy raz i usuwamy z paska adresu.
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

type ResolvedAuthState = Exclude<AuthState, { status: 'loading' }>;

async function fetchCurrentUser(): Promise<ResolvedAuthState> {
  try {
    const response = await apiFetch('/auth/me');
    if (response.ok) {
      const user = (await response.json()) as AuthUser;
      return { status: 'authenticated', user };
    }
    const code = await readAuthErrorCode(response);
    if (response.status === 401) {
      // brak sesji przy starcie to normalny stan, nie blad do pokazania
      return { status: 'unauthenticated', error: code === 'not_authenticated' ? null : code };
    }
    return { status: 'unauthenticated', error: code ?? 'provider_unavailable' };
  } catch {
    return { status: 'unauthenticated', error: 'provider_unavailable' };
  }
}

// full navigation (not fetch) - the backend redirects on to Keycloak
function goToLogin(): void {
  redirecting = true;
  const storage = getSessionStorage();
  if (storage !== null) markRedirect(storage, Date.now());
  window.location.assign(`${API_BASE_URL}/auth/login`);
}

// Without a session: go straight to Keycloak (returns null) or, for real errors
// and when the loop guard trips, return the login screen state to show.
function redirectOrShow(error: LoginError | null): ResolvedAuthState | null {
  if (redirecting) return null;
  const storage = getSessionStorage();
  if (storage === null) {
    // no sessionStorage = no loop guard, so never redirect on our own
    return { status: 'unauthenticated', error: error === 'not_authenticated' ? null : error };
  }
  if (shouldAutoRedirect(error, readLastRedirect(storage), Date.now())) {
    goToLogin();
    return null;
  }
  return { status: 'unauthenticated', error: NO_SESSION_ERRORS.has(error) ? 'login_incomplete' : error };
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    const urlError = authErrorFromUrlOnce();

    fetchCurrentUser().then((result) => {
      if (cancelled) return;
      if (result.status === 'authenticated') {
        const storage = getSessionStorage();
        if (storage !== null) clearRedirectMark(storage);
        claimChatStorage(result.user.id);
        setState(result);
        return;
      }
      // null = the browser is already on its way to Keycloak, keep the spinner
      const next = redirectOrShow(urlError ?? result.error);
      if (next !== null) setState(next);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  // backend odrzucil sesje w trakcie pracy (wygasla / usuniety z grupy)
  useEffect(() => {
    const onSessionLost = (event: Event) => {
      const code = (event as CustomEvent<AuthErrorCode>).detail;
      if (code === 'not_member') clearChatStorage();
      // expired session: back through Keycloak (usually invisible thanks to SSO)
      setState(redirectOrShow(code) ?? { status: 'loading' });
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

  const login = useCallback(() => {
    goToLogin();
  }, []);

  const logout = useCallback(async () => {
    clearChatStorage();
    let logoutUrl: string | null = null;
    try {
      const response = await apiFetch('/auth/logout', { method: 'POST' });
      if (response.ok) {
        logoutUrl = ((await response.json()) as LogoutResponse).logout_url;
      }
    } catch {
      // sesja i tak jest bezuzyteczna po stronie przegladarki
    }
    if (logoutUrl) {
      // konczy tez sesje w Keycloaku i wraca na strone glowna
      window.location.assign(logoutUrl);
      return;
    }
    setState({ status: 'unauthenticated', error: null });
  }, []);

  return { state, login, logout };
}
