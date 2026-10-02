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

// A non-2xx API response. `code` is the login error code from the body, if
// any; `detail` is the raw `detail` of a JSON body (e.g. the daily limit info
// of a 429) and `retryAfter` the Retry-After header, for callers that need them.
export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: AuthErrorCode | null;
  readonly detail: unknown;
  readonly retryAfter: string | null;

  constructor(status: number, code: AuthErrorCode | null, detail: unknown = null, retryAfter: string | null = null) {
    super(`API request failed with HTTP ${status}`);
    this.name = 'ApiRequestError';
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.retryAfter = retryAfter;
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

async function readErrorDetail(response: Response): Promise<unknown> {
  try {
    const { detail } = (await response.json()) as ErrorBody;
    return detail ?? null;
  } catch {
    // response without JSON (e.g. a 502 from nginx) has no detail
    return null;
  }
}

function authErrorCodeOf(detail: unknown): AuthErrorCode | null {
  if (typeof detail === 'object' && detail !== null && 'code' in detail) {
    const { code } = detail as { code: unknown };
    return isAuthErrorCode(code) ? code : null;
  }
  return null;
}

// The error for a non-2xx response (also used by requests made without fetch,
// e.g. uploads with progress); a lost session is announced with SESSION_LOST_EVENT.
export function apiErrorFrom(status: number, detail: unknown, retryAfter: string | null): ApiRequestError {
  const code = authErrorCodeOf(detail);
  const error = new ApiRequestError(status, code, detail, retryAfter);
  if (error.sessionLost && code !== null) {
    window.dispatchEvent(new CustomEvent<AuthErrorCode>(SESSION_LOST_EVENT, { detail: code }));
  }
  return error;
}

// fetch to the API with the session cookie. Throws ApiRequestError for a
// non-2xx response; a lost session is also announced with SESSION_LOST_EVENT.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', ...init });
  if (response.ok) return response;
  const detail = await readErrorDetail(response);
  throw apiErrorFrom(response.status, detail, response.headers.get('Retry-After'));
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  return (await response.json()) as T;
}
