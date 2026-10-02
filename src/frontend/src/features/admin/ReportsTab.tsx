import { useCallback, useId, useState } from 'react';
import { ChevronDown, Download } from 'lucide-react';
import { sourceHref } from '../chat/sources';
import type { Translation } from '../preferences/languages';
import {
  PAGE_SIZE,
  feedbackExportUrl,
  fetchReports,
  reviewReport,
  type AdminReport,
  type ReviewUpdate,
} from './adminApi';
import { LoadError, LoadingRow, Pagination, StatusBadge } from './AdminCommon';
import { formatDateTime } from './format';
import ReviewForm from './ReviewForm';
import StatusFilter from './StatusFilter';
import { CARD, HINT, LABEL, SMALL_BUTTON } from './styles';
import { useLoader } from './useLoader';

interface ReportsTabProps {
  lang: Translation;
}

function ReportDetails({ lang, report }: { lang: Translation; report: AdminReport }) {
  const text = lang.admin;
  return (
    <dl className="flex flex-col gap-3 text-sm">
      {report.answerGone && <p className={HINT}>{text.answerGone}</p>}
      <div>
        <dt className={LABEL}>{text.question}</dt>
        <dd className="mt-1 whitespace-pre-wrap break-words">{report.question ?? text.noQuestion}</dd>
      </div>
      <div>
        <dt className={LABEL}>{text.answer}</dt>
        <dd className="mt-1 whitespace-pre-wrap break-words rounded-control bg-surface-sunken p-3">{report.answer}</dd>
      </div>
      {report.sources.length > 0 && (
        <div>
          <dt className={LABEL}>{lang.sources(report.sources.length)}</dt>
          <dd>
            <ul className="mt-1 flex flex-col gap-1">
              {report.sources.map((source, index) => {
                const href = sourceHref(source);
                return (
                  <li key={`${source.kind}-${index}`} className="break-words">
                    <span className="text-muted">{lang.sourceKinds[source.kind]}: </span>
                    {href !== null ? (
                      <a href={href} target="_blank" rel="noopener noreferrer" className="ksi-link font-normal">
                        {source.title}
                      </a>
                    ) : (
                      source.title
                    )}
                  </li>
                );
              })}
            </ul>
          </dd>
        </div>
      )}
      {report.comment !== null && (
        <div>
          <dt className={LABEL}>{text.comment}</dt>
          <dd className="mt-1 whitespace-pre-wrap break-words">{report.comment}</dd>
        </div>
      )}
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        <div>
          <dt className={`${HINT} inline`}>{text.answerLanguage}: </dt>
          <dd className="inline text-xs uppercase">{report.language ?? '—'}</dd>
        </div>
        {report.reviewedAt !== null && (
          <div>
            <dt className={`${HINT} inline`}>{text.reviewedAt}: </dt>
            <dd className="inline text-xs">{formatDateTime(report.reviewedAt, lang.htmlLang)}</dd>
          </div>
        )}
      </div>
    </dl>
  );
}

function ReportCard({ lang, report, onReview }: {
  lang: Translation;
  report: AdminReport;
  onReview: (update: ReviewUpdate) => Promise<boolean>;
}) {
  const text = lang.admin;
  const [isOpen, setIsOpen] = useState(false);
  const detailsId = useId();
  const reason = report.reason !== null ? lang.reportReasons[report.reason] : text.unknown;

  return (
    <li className={`${CARD} flex flex-col gap-2`}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge text={text} status={report.status} />
        <span className="text-sm font-semibold">{reason}</span>
        <span className="text-xs text-muted">{formatDateTime(report.reportedAt ?? report.createdAt, lang.htmlLang)}</span>
      </div>
      <p className="text-sm break-words line-clamp-2">{report.question ?? text.noQuestion}</p>
      {report.comment !== null && !isOpen && <p className="text-sm text-muted break-words line-clamp-2">“{report.comment}”</p>}
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-controls={detailsId}
        className={`${SMALL_BUTTON} self-start`}
      >
        <ChevronDown size={14} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
        {isOpen ? text.hideDetails : text.showDetails}
      </button>
      {isOpen && (
        <div id={detailsId} className="flex flex-col gap-3">
          <ReportDetails lang={lang} report={report} />
          <ReviewForm key={`${report.status}-${report.adminNote}`} text={text} status={report.status} note={report.adminNote} onSubmit={onReview} />
        </div>
      )}
    </li>
  );
}

// Answer reports from users: open ones first by default, review with a note,
// CSV export of the snapshots (material for the evaluation set).
export default function ReportsTab({ lang }: ReportsTabProps) {
  const text = lang.admin;
  const [status, setStatus] = useState<AdminReport['status']>('open');
  const [offset, setOffset] = useState(0);
  const load = useCallback(() => fetchReports(status, offset), [status, offset]);
  const reports = useLoader(load);
  const { update } = reports;

  const review = useCallback(async (id: string, change: ReviewUpdate): Promise<boolean> => {
    try {
      const saved = await reviewReport(id, change);
      update((page) => ({ ...page, items: page.items.map((item) => (item.id === id ? saved : item)) }));
      return true;
    } catch {
      return false;
    }
  }, [update]);

  const changeStatus = (next: AdminReport['status']) => {
    setStatus(next);
    setOffset(0);
  };

  const page = reports.data;
  return (
    <section className="flex flex-col gap-4" aria-busy={reports.isLoading}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <StatusFilter text={text} value={status} onChange={changeStatus} />
        <a href={feedbackExportUrl(status)} download className="ksi-btn ksi-btn-secondary">
          <Download size={14} aria-hidden="true" />
          {text.exportCsv}
        </a>
      </div>

      {reports.hasError && <LoadError text={text} retryLabel={lang.retry} onRetry={reports.reload} />}
      {reports.isLoading && page === null && <LoadingRow label={lang.loading} />}
      {page !== null && page.items.length === 0 && !reports.isLoading && <p className="text-sm text-muted">{text.noReports}</p>}
      {page !== null && page.items.length > 0 && (
        <ul className={`flex flex-col gap-3 ${reports.isLoading ? 'opacity-60' : ''}`}>
          {page.items.map((report) => (
            <ReportCard key={report.id} lang={lang} report={report} onReview={(change) => review(report.id, change)} />
          ))}
        </ul>
      )}
      {page !== null && (
        <Pagination text={text} offset={page.offset} count={page.items.length} total={page.total} pageSize={PAGE_SIZE} onOffset={setOffset} />
      )}
    </section>
  );
}
