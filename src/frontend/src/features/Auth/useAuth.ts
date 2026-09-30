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

export interface AuthUser {
  id: string;
  email: string | null;
  username: string | null;
  name: string | null;
}

export type AuthState =
  | { status: 'loading' }
  | { status: 'authenticated'; user: AuthUser }
  | { status: 'unauthenticated'; error: AuthErrorCode | null };

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

export function useAuth() {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    const urlError = takeAuthErrorFromUrl();

    fetchCurrentUser().then((result) => {
      if (cancelled) return;
      if (result.status === 'authenticated') {
        claimChatStorage(result.user.id);
        setState(result);
      } else {
        setState({ status: 'unauthenticated', error: urlError ?? result.error });
      }
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
      setState({ status: 'unauthenticated', error: code === 'not_authenticated' ? 'session_expired' : code });
    };
    window.addEventListener(SESSION_LOST_EVENT, onSessionLost);
    return () => window.removeEventListener(SESSION_LOST_EVENT, onSessionLost);
  }, []);

  // pelne przekierowanie (nie fetch) - backend odsyla do Keycloaka
  const login = useCallback(() => {
    window.location.assign(`${API_BASE_URL}/auth/login`);
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
