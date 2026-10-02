import { AlertCircle, Download, FileImage, FileText, FileType, Loader2, X, type LucideIcon } from 'lucide-react';
import type { AttachmentType } from '../admin/adminApi';
import type { Translation } from '../preferences/languages';
import { attachmentUrl, formatFileSize, type AttachmentMeta } from './attachments';
import { describeAttachmentProblem } from './attachmentText';
import type { PendingUpload } from './uploads';

const KIND_ICONS: Record<AttachmentType, LucideIcon> = {
  pdf: FileText,
  docx: FileType,
  txt: FileText,
  png: FileImage,
  jpeg: FileImage,
  webp: FileImage,
};

const CHIP = 'flex items-center gap-2 min-w-0 max-w-full rounded-control border px-2.5 py-1.5 text-xs';

interface PendingChipsProps {
  lang: Translation;
  items: readonly PendingUpload[];
  onRemove: (localId: string) => void;
}

// Chips above the question input: uploading (with progress), ready or failed.
export function PendingChips({ lang, items, onRemove }: PendingChipsProps) {
  if (items.length === 0) return null;
  const text = lang.attachments;
  return (
    <ul aria-label={text.list} className="flex flex-wrap gap-2 mb-2">
      {items.map((item) => {
        const Icon = item.status === 'failed' ? AlertCircle : KIND_ICONS[item.kind];
        const percent = Math.round(item.progress * 100);
        const isFailed = item.status === 'failed';
        const isUploading = item.status === 'uploading';
        return (
          <li
            key={item.localId}
            className={`${CHIP} ${isFailed ? 'ksi-alert-danger' : 'border-line bg-surface'} relative overflow-hidden`}
          >
            {isUploading && (
              <span
                aria-hidden="true"
                className="absolute inset-y-0 left-0 bg-surface-hover transition-[width] duration-150"
                style={{ width: `${percent}%` }}
              />
            )}
            <span className="relative flex items-center gap-2 min-w-0">
              {isUploading ? (
                <Loader2 size={14} className="shrink-0 animate-spin text-muted" aria-hidden="true" />
              ) : (
                <Icon size={14} className={`shrink-0 ${isFailed ? 'text-danger-text' : 'text-muted'}`} aria-hidden="true" />
              )}
              <span className="flex flex-col min-w-0">
                <span className="truncate text-fg max-w-48" title={item.name}>{item.name}</span>
                <span className={isFailed ? 'text-danger-text break-words' : 'text-muted'}>
                  {isFailed && item.problem
                    ? describeAttachmentProblem(item.problem, lang)
                    : isUploading
                      ? text.uploading(percent)
                      : formatFileSize(item.size, lang.htmlLang)}
                </span>
              </span>
            </span>
            <button
              type="button"
              onClick={() => onRemove(item.localId)}
              className="relative shrink-0 p-0.5 rounded-control text-muted transition-colors hover:bg-surface-hover hover:text-fg"
              title={isUploading ? text.cancel(item.name) : text.remove(item.name)}
              aria-label={isUploading ? text.cancel(item.name) : text.remove(item.name)}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

interface SentChipsProps {
  lang: Translation;
  attachments: readonly AttachmentMeta[];
}

// Files of a sent question; a click downloads the file.
export function SentChips({ lang, attachments }: SentChipsProps) {
  return (
    <ul aria-label={lang.attachments.list} className="flex flex-wrap justify-end gap-2">
      {attachments.map((attachment) => {
        const Icon = KIND_ICONS[attachment.type];
        return (
          <li key={attachment.id} className="min-w-0 max-w-full">
            <a
              href={attachmentUrl(attachment.id)}
              download={attachment.name}
              title={lang.attachments.download(attachment.name)}
              aria-label={lang.attachments.download(attachment.name)}
              className={`${CHIP} border-line bg-surface text-fg transition-colors hover:bg-surface-hover`}
            >
              <Icon size={14} className="shrink-0 text-muted" aria-hidden="true" />
              <span className="truncate max-w-48">{attachment.name}</span>
              <span className="shrink-0 text-muted">{formatFileSize(attachment.size, lang.htmlLang)}</span>
              <Download size={12} className="shrink-0 text-muted" aria-hidden="true" />
            </a>
          </li>
        );
      })}
    </ul>
  );
}
