import { Loader2, RefreshCw } from 'lucide-react';
import type { AdminTranslation } from '../preferences/languages';
import type { ReviewStatus } from './adminApi';
import { BADGE } from './styles';

export function LoadingRow({ label }: { label: string }) {
  return (
    <div role="status" className="flex justify-center py-8">
      <Loader2 className="w-5 h-5 animate-spin text-muted" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

interface LoadErrorProps {
  text: AdminTranslation;
  retryLabel: string;
  onRetry: () => void;
}

export function LoadError({ text, retryLabel, onRetry }: LoadErrorProps) {
  return (
    <div role="alert" className="ksi-alert-danger rounded-card flex flex-wrap items-center justify-between gap-3 p-3">
      <span className="text-sm text-danger-text">{text.loadError}</span>
      <button type="button" onClick={onRetry} className="ksi-btn ksi-btn-secondary">
        <RefreshCw size={14} aria-hidden="true" />
        {retryLabel}
      </button>
    </div>
  );
}

const STATUS_STYLES: Record<ReviewStatus, string> = {
  open: 'border-line-strong text-fg bg-accent-soft',
  resolved: 'border-line text-muted',
  dismissed: 'border-line text-faint',
};

export function StatusBadge({ text, status }: { text: AdminTranslation; status: ReviewStatus | null }) {
  if (status === null) return <span className={`${BADGE} border-line text-faint`}>{text.unknown}</span>;
  return <span className={`${BADGE} ${STATUS_STYLES[status]}`}>{text.statuses[status]}</span>;
}

interface PaginationProps {
  text: AdminTranslation;
  offset: number;
  count: number;
  total: number;
  pageSize: number;
  onOffset: (offset: number) => void;
}

// "1-20 of 45" with previous / next; hidden when everything fits on one page.
export function Pagination({ text, offset, count, total, pageSize, onOffset }: PaginationProps) {
  if (total <= pageSize && offset === 0) return null;
  const from = count === 0 ? 0 : offset + 1;
  return (
    <nav className="flex flex-wrap items-center justify-between gap-2 pt-3" aria-label={text.pageInfo(from, offset + count, total)}>
      <span className="text-xs text-muted tabular-nums">{text.pageInfo(from, offset + count, total)}</span>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onOffset(Math.max(0, offset - pageSize))}
          disabled={offset === 0}
          className="ksi-btn ksi-btn-secondary disabled:opacity-50"
        >
          {text.previousPage}
        </button>
        <button
          type="button"
          onClick={() => onOffset(offset + pageSize)}
          disabled={offset + count >= total}
          className="ksi-btn ksi-btn-secondary disabled:opacity-50"
        >
          {text.nextPage}
        </button>
      </div>
    </nav>
  );
}
