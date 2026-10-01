// The frontend always calls the backend through /api on its own origin: nginx
// proxies it in Docker (nginx.conf), Vite in `npm run dev` (vite.config.ts).
// One origin means the session cookie works without CORS.
export const API_BASE_URL = '/api';

// Login error codes: the backend returns them in detail.code (401/403/503) or
// in ?auth_error= after coming back from Keycloak.
const AUTH_ERROR_CODES = [
  'not_authenticated',
  'session_expired',
  'not_member',
  'provider_unavailable',
  'access_denied',
  'invalid_state',
  'login_failed',
  'forbidden_origin',
] as const;

export type AuthErrorCode = (typeof AUTH_ERROR_CODES)[number];

export function isAuthErrorCode(value: unknown): value is AuthErrorCode {
  return typeof value === 'string' && (AUTH_ERROR_CODES as readonly string[]).includes(value);
}

// Codes after which the session in this browser is no longer usable.
const SESSION_LOST_CODES: ReadonlySet<AuthErrorCode> = new Set<AuthErrorCode>([
  'not_authenticated',
  'session_expired',
  'not_member',
]);

// Dispatched when the backend rejects the session mid-use (expired, removed
// from the group) - useAuth then switches to the login flow.
export const SESSION_LOST_EVENT = 'chatbot:session-lost';

// A non-2xx API response. `code` is the login error code from the body, if any.
export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: AuthErrorCode | null;

  constructor(status: number, code: AuthErrorCode | null) {
    super(`API request failed with HTTP ${status}`);
    this.name = 'ApiRequestError';
    this.status = status;
    this.code = code;
  }

  // True when SESSION_LOST_EVENT was dispatched for this response.
  get sessionLost(): boolean {
    return (this.status === 401 || this.status === 403) && this.code !== null && SESSION_LOST_CODES.has(this.code);
  }
}

export function isSessionLost(error: unknown): boolean {
  return error instanceof ApiRequestError && error.sessionLost;
}

interface ErrorBody {
  detail?: unknown;
}

async function readAuthErrorCode(response: Response): Promise<AuthErrorCode | null> {
  try {
    const { detail } = (await response.json()) as ErrorBody;
    if (typeof detail === 'object' && detail !== null && 'code' in detail) {
      const { code } = detail as { code: unknown };
      return isAuthErrorCode(code) ? code : null;
    }
  } catch {
    // response without JSON (e.g. a 502 from nginx) has no code
  }
  return null;
}

// fetch to the API with the session cookie. Throws ApiRequestError for a
// non-2xx response; a lost session is also announced with SESSION_LOST_EVENT.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', ...init });
  if (response.ok) return response;
  const code = await readAuthErrorCode(response);
  const error = new ApiRequestError(response.status, code);
  if (error.sessionLost && code !== null) {
    window.dispatchEvent(new CustomEvent<AuthErrorCode>(SESSION_LOST_EVENT, { detail: code }));
  }
  throw error;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  return (await response.json()) as T;
}
