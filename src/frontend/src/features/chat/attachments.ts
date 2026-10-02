import { API_BASE_URL, ApiRequestError, apiErrorFrom, apiFetch } from '../../lib/api';
import { ATTACHMENT_TYPES, type AttachmentType } from '../admin/adminApi';

// Files attached to a question: limits from GET /usage, client-side pre-checks,
// upload (POST /attachments, raw body + X-Filename, with progress), delete and
// download links. The server checks everything again (type by content, sizes,
// daily limit) - the pre-checks only save a round trip.

// A file sent with (or ready for) a question.
export interface AttachmentMeta {
  id: string;
  name: string;
  size: number;
  type: AttachmentType;
}

export interface AttachmentLimits {
  maxFileMb: number;
  // images have a lower cap (min of 5 MB and maxFileMb)
  maxImageMb: number;
  maxFilesPerMessage: number;
  // 0 = attachments switched off by the admins
  maxPerDay: number;
  usedToday: number;
  allowedTypes: AttachmentType[];
  // false = the current model cannot see images
  imagesSupported: boolean;
}

// Why a file was refused (client check or server answer) or a send failed.
export type AttachmentProblem =
  | { code: 'too_large'; name?: string; maxMb?: number }
  | { code: 'empty'; name: string }
  | { code: 'unsupported_type'; name: string }
  | { code: 'unreadable'; name: string }
  | { code: 'upload_failed'; name: string }
  | { code: 'images_unsupported'; name?: string }
  | { code: 'too_many'; maxFiles: number }
  | { code: 'daily_limit'; limit: number; resetAt: string }
  | { code: 'disabled' }
  | { code: 'not_found' }
  | { code: 'chat_disabled' }
  | { code: 'upload_timeout'; name: string }
  // too many uploads at once (the input queues them, so this is rare)
  | { code: 'busy' }
  // too many unsent files - send the question or remove some
  | { code: 'storage_full' }
  // the server is out of disk space
  | { code: 'storage_unavailable' };

// Uploads running at the same time (the server refuses more with uploads_busy).
export const MAX_PARALLEL_UPLOADS = 2;

// Anything with a name, size and MIME type - a File, or a plain object in tests.
export interface FileLike {
  name: string;
  size: number;
  type: string;
}

const MB = 1024 * 1024;
const KB = 1024;

const EXTENSIONS: Record<AttachmentType, readonly string[]> = {
  pdf: ['.pdf'],
  docx: ['.docx'],
  txt: ['.txt'],
  png: ['.png'],
  jpeg: ['.jpg', '.jpeg'],
  webp: ['.webp'],
};

const MIME_KINDS: Readonly<Record<string, AttachmentType>> = {
  'application/pdf': 'pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'text/plain': 'txt',
  'image/png': 'png',
  'image/jpeg': 'jpeg',
  'image/webp': 'webp',
};

const IMAGE_KINDS: ReadonlySet<AttachmentType> = new Set<AttachmentType>(['png', 'jpeg', 'webp']);

export function isImageKind(kind: AttachmentType): boolean {
  return IMAGE_KINDS.has(kind);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function asKind(value: unknown): AttachmentType | null {
  return ATTACHMENT_TYPES.find((kind) => kind === value) ?? null;
}

// The "attachments" block of GET /usage; null when missing or malformed.
export function parseAttachmentLimits(value: unknown): AttachmentLimits | null {
  if (!isRecord(value)) return null;
  const { max_file_mb, max_image_mb, max_files_per_message, max_per_day, used_today, allowed_types, images_supported } =
    value;
  if (
    !isCount(max_file_mb) || !isCount(max_image_mb) || !isCount(max_files_per_message) || !isCount(max_per_day) ||
    !isCount(used_today) || !Array.isArray(allowed_types) || typeof images_supported !== 'boolean'
  ) {
    return null;
  }
  return {
    maxFileMb: max_file_mb,
    maxImageMb: max_image_mb,
    maxFilesPerMessage: max_files_per_message,
    maxPerDay: max_per_day,
    usedToday: used_today,
    allowedTypes: allowed_types.map(asKind).filter((kind): kind is AttachmentType => kind !== null),
    imagesSupported: images_supported,
  };
}

export function parseAttachmentMeta(value: unknown): AttachmentMeta | null {
  if (!isRecord(value)) return null;
  const { id, name, size, type } = value;
  const kind = asKind(type);
  if (typeof id !== 'string' || typeof name !== 'string' || !isCount(size) || kind === null) return null;
  return { id, name, size, type: kind };
}

// Attachments of a user message in GET /conversations/{id}; bad entries are skipped.
export function parseAttachmentList(value: unknown): AttachmentMeta[] {
  if (!Array.isArray(value)) return [];
  return value.map(parseAttachmentMeta).filter((meta): meta is AttachmentMeta => meta !== null);
}

// Kind by extension, then by the browser's MIME type. Only a hint - the server
// decides by the file content.
export function kindOfFile(file: FileLike): AttachmentType | null {
  const lower = file.name.toLowerCase();
  const byExtension = ATTACHMENT_TYPES.find((kind) => EXTENSIONS[kind].some((ext) => lower.endsWith(ext)));
  return byExtension ?? MIME_KINDS[file.type] ?? null;
}

// `accept` of the file input: extensions of the types usable right now.
export function acceptList(limits: AttachmentLimits): string {
  return limits.allowedTypes
    .filter((kind) => limits.imagesSupported || !isImageKind(kind))
    .flatMap((kind) => EXTENSIONS[kind])
    .join(',');
}

function problemOfFile(file: FileLike, limits: AttachmentLimits): AttachmentProblem | null {
  const kind = kindOfFile(file);
  if (kind === null || !limits.allowedTypes.includes(kind)) return { code: 'unsupported_type', name: file.name };
  if (isImageKind(kind) && !limits.imagesSupported) return { code: 'images_unsupported', name: file.name };
  if (file.size === 0) return { code: 'empty', name: file.name };
  const maxMb = isImageKind(kind) ? limits.maxImageMb : limits.maxFileMb;
  if (file.size > maxMb * MB) return { code: 'too_large', name: file.name, maxMb };
  return null;
}

export interface FileCheck<T extends FileLike> {
  accepted: T[];
  problems: AttachmentProblem[];
}

// Pre-checks of files being added next to `current` chips: type, size and the
// per-message count (extra files are dropped with one "too many" problem).
export function checkFiles<T extends FileLike>(files: readonly T[], current: number, limits: AttachmentLimits): FileCheck<T> {
  if (limits.maxPerDay === 0) return { accepted: [], problems: [{ code: 'disabled' }] };
  const accepted: T[] = [];
  const problems: AttachmentProblem[] = [];
  let tooMany = false;
  for (const file of files) {
    const problem = problemOfFile(file, limits);
    if (problem !== null) {
      problems.push(problem);
    } else if (current + accepted.length >= limits.maxFilesPerMessage) {
      tooMany = true;
    } else {
      accepted.push(file);
    }
  }
  if (tooMany) problems.push({ code: 'too_many', maxFiles: limits.maxFilesPerMessage });
  return { accepted, problems };
}

// "900 B", "1.5 KB", "10 MB" - one decimal at most, in the interface locale.
export function formatFileSize(bytes: number, locale: string): string {
  if (bytes < KB) return `${bytes} B`;
  const [value, unit] = bytes < MB ? [bytes / KB, 'KB'] : [bytes / MB, 'MB'];
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value);
  return `${number} ${unit}`;
}

function numberField(detail: Record<string, unknown>, key: string): number | undefined {
  const value = detail[key];
  return isCount(value) ? value : undefined;
}

// What an API error says about attachments: upload errors (with the file name)
// and send errors (404/422 before the stream). null = not about attachments.
export function attachmentProblemOf(error: unknown, name?: string): AttachmentProblem | null {
  if (!(error instanceof ApiRequestError)) return name === undefined ? null : { code: 'upload_failed', name };
  const detail = isRecord(error.detail) ? error.detail : {};
  switch (detail.code) {
    case 'file_too_large': {
      const maxMb = numberField(detail, 'max_mb');
      return { code: 'too_large', ...(name !== undefined ? { name } : {}), ...(maxMb !== undefined ? { maxMb } : {}) };
    }
    case 'empty_file':
      return { code: 'empty', name: name ?? '' };
    case 'unsupported_type':
      return { code: 'unsupported_type', name: name ?? '' };
    case 'unreadable_file':
      return { code: 'unreadable', name: name ?? '' };
    case 'attachments_limited': {
      const limit = numberField(detail, 'limit');
      const resetAt = typeof detail.reset_at === 'string' ? detail.reset_at : null;
      return limit !== undefined && resetAt !== null ? { code: 'daily_limit', limit, resetAt } : { code: 'disabled' };
    }
    case 'attachments_disabled':
      return { code: 'disabled' };
    case 'images_unsupported':
      return { code: 'images_unsupported' };
    case 'too_many_files':
      return { code: 'too_many', maxFiles: numberField(detail, 'max_files') ?? 0 };
    case 'attachment_not_found':
      return { code: 'not_found' };
    case 'chat_disabled':
      return name === undefined ? null : { code: 'chat_disabled' };
    case 'upload_timeout':
      return { code: 'upload_timeout', name: name ?? '' };
    case 'uploads_busy':
      return { code: 'busy' };
    case 'attachments_storage_full':
      return { code: 'storage_full' };
    case 'storage_unavailable':
      return { code: 'storage_unavailable' };
    default:
      break;
  }
  if (error.status === 413) return { code: 'too_large', ...(name !== undefined ? { name } : {}) };
  return name === undefined ? null : { code: 'upload_failed', name };
}

function readJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

// Uploads one file with progress (fetch has no upload progress, hence XHR).
// Resolves to the stored attachment; rejects with ApiRequestError for an HTTP
// error, an AbortError when `signal` aborts, or an Error for a network failure.
export function uploadAttachment(
  file: File,
  onProgress: (fraction: number) => void,
  signal: AbortSignal,
): Promise<AttachmentMeta> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/attachments`);
    xhr.withCredentials = true;
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      const body = readJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        const meta = parseAttachmentMeta(body);
        if (meta !== null) resolve(meta);
        else reject(new Error('Invalid upload response'));
        return;
      }
      const detail = isRecord(body) ? body.detail ?? null : null;
      reject(apiErrorFrom(xhr.status, detail, xhr.getResponseHeader('Retry-After')));
    };
    xhr.onerror = () => reject(new Error('Upload failed'));
    xhr.onabort = () => reject(new DOMException('Upload aborted', 'AbortError'));
    if (signal.aborted) {
      reject(new DOMException('Upload aborted', 'AbortError'));
      return;
    }
    signal.addEventListener('abort', () => xhr.abort(), { once: true });
    xhr.send(file);
  });
}

// Deletes an unsent attachment; already gone counts as deleted.
export async function deleteAttachment(id: string): Promise<void> {
  try {
    await apiFetch(`/attachments/${encodeURIComponent(id)}`, { method: 'DELETE' });
  } catch (error) {
    if (!(error instanceof ApiRequestError && error.status === 404)) throw error;
  }
}

// Download link (the server answers with Content-Disposition: attachment).
export function attachmentUrl(id: string): string {
  return `${API_BASE_URL}/attachments/${encodeURIComponent(id)}`;
}
