// Frontend zawsze woła backend przez /api na wlasnym originie: w Dockerze
// proxy robi nginx (src/frontend/nginx.conf), w `npm run dev` - vite
// (vite.config.ts). Jeden origin = ciasteczko sesji dziala bez CORS.
export const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? '/api';

// Kody bledow logowania - backend zwraca je w detail.code (401/403/503)
// albo w ?auth_error= po powrocie z Keycloaka.
export type AuthErrorCode =
  | 'not_authenticated'
  | 'session_expired'
  | 'not_member'
  | 'provider_unavailable'
  | 'access_denied'
  | 'invalid_state'
  | 'login_failed'
  | 'forbidden_origin';

const AUTH_ERROR_CODES: ReadonlySet<string> = new Set<AuthErrorCode>([
  'not_authenticated',
  'session_expired',
  'not_member',
  'provider_unavailable',
  'access_denied',
  'invalid_state',
  'login_failed',
  'forbidden_origin',
]);

export function isAuthErrorCode(value: unknown): value is AuthErrorCode {
  return typeof value === 'string' && AUTH_ERROR_CODES.has(value);
}

// Kody, po ktorych sesja w przegladarce jest juz bezuzyteczna.
const SESSION_LOST_CODES: ReadonlySet<AuthErrorCode> = new Set<AuthErrorCode>([
  'not_authenticated',
  'session_expired',
  'not_member',
]);

// Zdarzenie wysylane, gdy backend odrzuci sesje w trakcie pracy (np. ktos
// zostal usuniety z grupy) - useAuth przelacza wtedy na ekran logowania.
export const SESSION_LOST_EVENT = 'chatbot:session-lost';

interface ErrorBody {
  detail?: unknown;
}

export async function readAuthErrorCode(response: Response): Promise<AuthErrorCode | null> {
  try {
    const body = (await response.clone().json()) as ErrorBody;
    const detail = body.detail;
    if (typeof detail === 'object' && detail !== null && 'code' in detail) {
      const code = (detail as { code: unknown }).code;
      return isAuthErrorCode(code) ? code : null;
    }
  } catch {
    // odpowiedz bez JSON-a (np. 502 z nginx) - brak kodu
  }
  return null;
}

// fetch do API z ciasteczkiem sesji. Utrata sesji (401/403 z kodem
// logowania) jest rozglaszana przez SESSION_LOST_EVENT; wolajacy i tak
// dostaje odpowiedz, zeby moc przerwac swoja prace.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', ...init });
  if (response.status === 401 || response.status === 403) {
    const code = await readAuthErrorCode(response);
    if (code !== null && SESSION_LOST_CODES.has(code)) {
      window.dispatchEvent(new CustomEvent<AuthErrorCode>(SESSION_LOST_EVENT, { detail: code }));
    }
  }
  return response;
}
