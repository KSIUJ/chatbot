import { API_BASE_URL, apiFetch, apiJson } from '../../lib/api';
import { REPORT_REASONS, type ReportReason } from '../chat/feedback';
import { parseSources, type Source } from '../chat/sources';
import { bool, list, num, oneOf, optNum, optStr, record, str, strings, type JsonRecord } from './read';

// Admin panel API (only for the admin group; the server checks it again):
// limits (/admin/settings, /admin/users), answer reports (/admin/feedback),
// security incidents (/admin/incidents) and diagnostics (/admin/diagnostics).

export const ATTACHMENT_TYPES = ['pdf', 'docx', 'txt', 'png', 'jpeg', 'webp'] as const;
export type AttachmentType = (typeof ATTACHMENT_TYPES)[number];

export const REVIEW_STATUSES = ['open', 'resolved', 'dismissed'] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

export const INCIDENT_SOURCES = ['heuristic', 'model', 'both'] as const;
export type IncidentSource = (typeof INCIDENT_SOURCES)[number];

export const PAGE_SIZE = 20;

export interface AttachmentLimits {
  maxFileMb: number;
  maxFilesPerMessage: number;
  maxPerDay: number;
  allowedTypes: AttachmentType[];
}

export interface LimitSettings {
  dailyQuestionLimit: number;
  attachments: AttachmentLimits;
}

export interface NumberRange {
  min: number;
  max: number;
}

export interface SettingsRanges {
  dailyQuestionLimit: NumberRange;
  userDailyLimit: NumberRange;
  maxFileMb: NumberRange;
  maxFilesPerMessage: NumberRange;
  maxPerDay: NumberRange;
}

export interface AdminSettings extends LimitSettings {
  defaults: LimitSettings;
  availableTypes: AttachmentType[];
  ranges: SettingsRanges;
}

export interface UserOverride {
  unlimited: boolean;
  dailyLimit: number | null;
  note: string | null;
  updatedAt: string;
}

export interface AdminUser {
  id: string;
  name: string | null;
  username: string | null;
  email: string | null;
  lastLoginAt: string | null;
  usedToday: number;
  // null = unlimited
  effectiveLimit: number | null;
  override: UserOverride | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminReport {
  id: string;
  // the answer was deleted (conversation expired / regenerated): only the snapshot is left
  answerGone: boolean;
  reason: ReportReason | null;
  comment: string | null;
  status: ReviewStatus | null;
  adminNote: string | null;
  reportedAt: string | null;
  reviewedAt: string | null;
  question: string | null;
  answer: string;
  sources: Source[];
  language: string | null;
  createdAt: string;
}

export interface IncidentPerson {
  id: string;
  name: string | null;
  username: string | null;
  email: string | null;
}

export interface AdminIncident {
  id: string;
  // null = the account no longer exists
  user: IncidentPerson | null;
  question: string;
  source: IncidentSource | null;
  rules: string[];
  status: ReviewStatus | null;
  adminNote: string | null;
  reviewedAt: string | null;
  createdAt: string;
}

// One diagnostics value: null with the error text when that part is unavailable.
export interface Metric<T> {
  value: T | null;
  error: string | null;
}

export interface Diagnostics {
  generatedAt: string;
  llm: {
    provider: string;
    model: string;
    startedAt: string;
    uptimeSeconds: number;
    totalCalls: number;
    totalErrors: number;
    recentCalls: number;
    recentErrors: number;
    avgLatencyMs: number | null;
    p95LatencyMs: number | null;
    lastError: string | null;
    lastErrorAt: string | null;
  };
  usage: Record<'questionsToday' | 'questions7d' | 'activeUsersToday' | 'activeUsers7d', Metric<number>>;
  totals: Record<'users' | 'conversations' | 'messages' | 'openReports' | 'openIncidents', Metric<number>>;
  rag: {
    vectorCount: Metric<number>;
    lexicalCount: Metric<number>;
    lexicalSizeBytes: Metric<number>;
    lastIngestAt: Metric<string>;
  };
  storage: {
    databaseSizeBytes: Metric<number>;
    diskFreeBytes: Metric<number>;
    diskTotalBytes: Metric<number>;
  };
}

// ---- mappers ----

function attachmentTypes(source: JsonRecord, key: string): AttachmentType[] {
  return strings(source, key)
    .map((value) => oneOf(value, ATTACHMENT_TYPES))
    .filter((value): value is AttachmentType => value !== null);
}

function parseLimitSettings(value: unknown, path: string): LimitSettings {
  const body = record(value, path);
  const attachments = record(body.attachments, `${path}.attachments`);
  return {
    dailyQuestionLimit: num(body, 'daily_question_limit'),
    attachments: {
      maxFileMb: num(attachments, 'max_file_mb'),
      maxFilesPerMessage: num(attachments, 'max_files_per_message'),
      maxPerDay: num(attachments, 'max_per_day'),
      allowedTypes: attachmentTypes(attachments, 'allowed_types'),
    },
  };
}

function parseRange(value: unknown, path: string): NumberRange {
  const range = record(value, path);
  return { min: num(range, 'min'), max: num(range, 'max') };
}

export function parseAdminSettings(value: unknown): AdminSettings {
  const body = record(value, 'settings');
  const ranges = record(body.ranges, 'ranges');
  return {
    ...parseLimitSettings(body, 'settings'),
    defaults: parseLimitSettings(body.defaults, 'defaults'),
    availableTypes: attachmentTypes(body, 'available_types'),
    ranges: {
      dailyQuestionLimit: parseRange(ranges.daily_question_limit, 'ranges.daily_question_limit'),
      userDailyLimit: parseRange(ranges.user_daily_limit, 'ranges.user_daily_limit'),
      maxFileMb: parseRange(ranges.max_file_mb, 'ranges.max_file_mb'),
      maxFilesPerMessage: parseRange(ranges.max_files_per_message, 'ranges.max_files_per_message'),
      maxPerDay: parseRange(ranges.max_per_day, 'ranges.max_per_day'),
    },
  };
}

export function toSettingsPayload(settings: LimitSettings) {
  const { attachments } = settings;
  return {
    daily_question_limit: settings.dailyQuestionLimit,
    attachments: {
      max_file_mb: attachments.maxFileMb,
      max_files_per_message: attachments.maxFilesPerMessage,
      max_per_day: attachments.maxPerDay,
      allowed_types: [...attachments.allowedTypes],
    },
  };
}

function parsePage<T>(value: unknown, parseItem: (item: unknown) => T): Page<T> {
  const body = record(value, 'page');
  return {
    items: list(body, 'items').map(parseItem),
    total: num(body, 'total'),
    limit: num(body, 'limit'),
    offset: num(body, 'offset'),
  };
}

function parseOverride(value: unknown): UserOverride | null {
  if (value === null || value === undefined) return null;
  const body = record(value, 'override');
  return {
    unlimited: bool(body, 'unlimited'),
    dailyLimit: optNum(body, 'daily_limit'),
    note: optStr(body, 'note'),
    updatedAt: str(body, 'updated_at'),
  };
}

export function parseAdminUser(value: unknown): AdminUser {
  const body = record(value, 'user');
  return {
    id: str(body, 'id'),
    name: optStr(body, 'name'),
    username: optStr(body, 'username'),
    email: optStr(body, 'email'),
    lastLoginAt: optStr(body, 'last_login_at'),
    usedToday: num(body, 'used_today'),
    effectiveLimit: optNum(body, 'effective_limit'),
    override: parseOverride(body.override),
  };
}

export function parseUserPage(value: unknown): Page<AdminUser> {
  return parsePage(value, parseAdminUser);
}

export function parseReport(value: unknown): AdminReport {
  const body = record(value, 'report');
  return {
    id: str(body, 'id'),
    answerGone: optStr(body, 'message_id') === null,
    reason: oneOf(body.report_reason, REPORT_REASONS),
    comment: optStr(body, 'comment'),
    status: oneOf(body.report_status, REVIEW_STATUSES),
    adminNote: optStr(body, 'admin_note'),
    reportedAt: optStr(body, 'reported_at'),
    reviewedAt: optStr(body, 'reviewed_at'),
    question: optStr(body, 'question'),
    answer: str(body, 'answer'),
    sources: parseSources(body.sources),
    language: optStr(body, 'language'),
    createdAt: str(body, 'created_at'),
  };
}

export function parseReportPage(value: unknown): Page<AdminReport> {
  return parsePage(value, parseReport);
}

function parsePerson(value: unknown): IncidentPerson | null {
  if (value === null || value === undefined) return null;
  const body = record(value, 'incident.user');
  return { id: str(body, 'id'), name: optStr(body, 'name'), username: optStr(body, 'username'), email: optStr(body, 'email') };
}

export function parseIncident(value: unknown): AdminIncident {
  const body = record(value, 'incident');
  return {
    id: str(body, 'id'),
    user: parsePerson(body.user),
    question: str(body, 'question'),
    source: oneOf(body.source, INCIDENT_SOURCES),
    rules: strings(body, 'rules'),
    status: oneOf(body.status, REVIEW_STATUSES),
    adminNote: optStr(body, 'admin_note'),
    reviewedAt: optStr(body, 'reviewed_at'),
    createdAt: str(body, 'created_at'),
  };
}

export function parseIncidentPage(value: unknown): Page<AdminIncident> {
  return parsePage(value, parseIncident);
}

function numberMetric(section: JsonRecord, key: string, errorKey = 'error'): Metric<number> {
  return { value: optNum(section, key), error: optStr(section, errorKey) };
}

export function parseDiagnostics(value: unknown): Diagnostics {
  const body = record(value, 'diagnostics');
  const llm = record(body.llm, 'llm');
  const usage = record(body.usage, 'usage');
  const totals = record(body.totals, 'totals');
  const rag = record(body.rag, 'rag');
  const storage = record(body.storage, 'storage');
  return {
    generatedAt: str(body, 'generated_at'),
    llm: {
      provider: str(llm, 'provider'),
      model: str(llm, 'model'),
      startedAt: str(llm, 'started_at'),
      uptimeSeconds: num(llm, 'uptime_seconds'),
      totalCalls: num(llm, 'total_calls'),
      totalErrors: num(llm, 'total_errors'),
      recentCalls: num(llm, 'recent_calls'),
      recentErrors: num(llm, 'recent_errors'),
      avgLatencyMs: optNum(llm, 'avg_latency_ms'),
      p95LatencyMs: optNum(llm, 'p95_latency_ms'),
      lastError: optStr(llm, 'last_error'),
      lastErrorAt: optStr(llm, 'last_error_at'),
    },
    usage: {
      questionsToday: numberMetric(usage, 'questions_today'),
      questions7d: numberMetric(usage, 'questions_7d'),
      activeUsersToday: numberMetric(usage, 'active_users_today'),
      activeUsers7d: numberMetric(usage, 'active_users_7d'),
    },
    totals: {
      users: numberMetric(totals, 'users'),
      conversations: numberMetric(totals, 'conversations'),
      messages: numberMetric(totals, 'messages'),
      openReports: numberMetric(totals, 'open_reports'),
      openIncidents: numberMetric(totals, 'open_incidents'),
    },
    rag: {
      vectorCount: numberMetric(rag, 'vector_count', 'vector_error'),
      lexicalCount: numberMetric(rag, 'lexical_count', 'lexical_error'),
      lexicalSizeBytes: numberMetric(rag, 'lexical_size_bytes', 'lexical_error'),
      lastIngestAt: { value: optStr(rag, 'last_ingest_at'), error: optStr(rag, 'last_ingest_error') },
    },
    storage: {
      databaseSizeBytes: numberMetric(storage, 'database_size_bytes', 'database_error'),
      diskFreeBytes: numberMetric(storage, 'disk_free_bytes', 'disk_error'),
      diskTotalBytes: numberMetric(storage, 'disk_total_bytes', 'disk_error'),
    },
  };
}

// ---- per-user limit editor ----

export type LimitMode = 'global' | 'custom' | 'unlimited';

export interface LimitChoice {
  mode: LimitMode;
  dailyLimit: number;
  note: string;
}

// PUT body for the choice; null = back to the global limit (DELETE).
export function toLimitPayload(choice: LimitChoice) {
  if (choice.mode === 'global') return null;
  const note = choice.note.trim() === '' ? null : choice.note.trim();
  if (choice.mode === 'unlimited') return { unlimited: true, note };
  return { unlimited: false, daily_limit: choice.dailyLimit, note };
}

// ---- requests ----

const JSON_HEADERS = { 'Content-Type': 'application/json' };

function pageQuery(params: Record<string, string | number | null>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== '') query.set(key, String(value));
  }
  return query.toString();
}

export async function fetchSettings(): Promise<AdminSettings> {
  return parseAdminSettings(await apiJson<unknown>('/admin/settings'));
}

export async function saveSettings(settings: LimitSettings): Promise<AdminSettings> {
  const body = JSON.stringify(toSettingsPayload(settings));
  return parseAdminSettings(await apiJson<unknown>('/admin/settings', { method: 'PUT', headers: JSON_HEADERS, body }));
}

export async function fetchUsers(query: string, offset: number): Promise<Page<AdminUser>> {
  const params = pageQuery({ q: query.trim(), limit: PAGE_SIZE, offset });
  return parseUserPage(await apiJson<unknown>(`/admin/users?${params}`));
}

// Saves the choice; returns the updated user (null after going back to the global limit).
export async function saveUserLimit(userId: string, choice: LimitChoice): Promise<AdminUser | null> {
  const path = `/admin/users/${encodeURIComponent(userId)}/limit`;
  const payload = toLimitPayload(choice);
  if (payload === null) {
    await apiFetch(path, { method: 'DELETE' });
    return null;
  }
  return parseAdminUser(await apiJson<unknown>(path, { method: 'PUT', headers: JSON_HEADERS, body: JSON.stringify(payload) }));
}

export async function fetchReports(status: ReviewStatus | null, offset: number): Promise<Page<AdminReport>> {
  const params = pageQuery({ kind: 'reports', status, limit: PAGE_SIZE, offset });
  return parseReportPage(await apiJson<unknown>(`/admin/feedback?${params}`));
}

export interface ReviewUpdate {
  status: ReviewStatus;
  adminNote: string;
}

function reviewBody(update: ReviewUpdate): string {
  const note = update.adminNote.trim();
  return JSON.stringify({ status: update.status, admin_note: note === '' ? null : note });
}

export async function reviewReport(id: string, update: ReviewUpdate): Promise<AdminReport> {
  const path = `/admin/feedback/${encodeURIComponent(id)}`;
  return parseReport(await apiJson<unknown>(path, { method: 'PATCH', headers: JSON_HEADERS, body: reviewBody(update) }));
}

export async function fetchIncidents(status: ReviewStatus | null, offset: number): Promise<Page<AdminIncident>> {
  const params = pageQuery({ status, limit: PAGE_SIZE, offset });
  return parseIncidentPage(await apiJson<unknown>(`/admin/incidents?${params}`));
}

export async function reviewIncident(id: string, update: ReviewUpdate): Promise<AdminIncident> {
  const path = `/admin/incidents/${encodeURIComponent(id)}`;
  return parseIncident(await apiJson<unknown>(path, { method: 'PATCH', headers: JSON_HEADERS, body: reviewBody(update) }));
}

// The server keeps a snapshot for ~15 s; `refresh` asks for a new one.
export function diagnosticsPath(refresh: boolean): string {
  return refresh ? '/admin/diagnostics?refresh=1' : '/admin/diagnostics';
}

export async function fetchDiagnostics(refresh = false): Promise<Diagnostics> {
  return parseDiagnostics(await apiJson<unknown>(diagnosticsPath(refresh)));
}

// Plain link (the session cookie is sent): the browser downloads the file.
export function feedbackExportUrl(status: ReviewStatus | null): string {
  const params = pageQuery({ kind: 'reports', status });
  return `${API_BASE_URL}/admin/feedback/export.csv?${params}`;
}
