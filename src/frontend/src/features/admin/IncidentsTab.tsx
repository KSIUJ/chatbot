import { useCallback, useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import { PAGE_SIZE, fetchIncidents, reviewIncident, type AdminIncident, type ReviewStatus, type ReviewUpdate } from './adminApi';
import { LoadError, LoadingRow, Pagination, StatusBadge } from './AdminCommon';
import { formatDateTime, personLabel } from './format';
import ReviewForm from './ReviewForm';
import StatusFilter from './StatusFilter';
import { CARD, HINT, LABEL, SMALL_BUTTON } from './styles';
import { useLoader } from './useLoader';

interface IncidentsTabProps {
  lang: Translation;
}

function IncidentDetails({ lang, incident }: { lang: Translation; incident: AdminIncident }) {
  const text = lang.admin;
  const { user } = incident;
  return (
    <dl className="flex flex-col gap-3 text-sm">
      <div>
        <dt className={LABEL}>{text.person}</dt>
        <dd className="mt-1 break-words">
          {user === null ? (
            <span className="text-muted">{text.deletedAccount}</span>
          ) : (
            <span className="flex flex-col">
              {user.name !== null && <span>{user.name}</span>}
              {user.username !== null && <span className="text-muted">{user.username}</span>}
              {user.email !== null && (
                <a href={`mailto:${user.email}`} className="ksi-link font-normal self-start">
                  {user.email}
                </a>
              )}
            </span>
          )}
        </dd>
      </div>
      <div>
        <dt className={LABEL}>{text.question}</dt>
        <dd className="mt-1 whitespace-pre-wrap break-words rounded-control bg-surface-sunken p-3">{incident.question}</dd>
      </div>
      <div>
        <dt className={LABEL}>{text.rules}</dt>
        <dd className="mt-1 flex flex-wrap gap-1.5">
          {incident.rules.length === 0 ? (
            <span className="text-muted">—</span>
          ) : (
            incident.rules.map((rule) => (
              <code key={rule} className="rounded-control border border-line bg-surface-sunken px-1.5 py-0.5 text-xs">
                {rule}
              </code>
            ))
          )}
        </dd>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        <div>
          <dt className={`${HINT} inline`}>{text.detectedBy}: </dt>
          <dd className="inline text-xs">{incident.source !== null ? text.incidentSources[incident.source] : text.unknown}</dd>
        </div>
        {incident.reviewedAt !== null && (
          <div>
            <dt className={`${HINT} inline`}>{text.reviewedAt}: </dt>
            <dd className="inline text-xs">{formatDateTime(incident.reviewedAt, lang.htmlLang)}</dd>
          </div>
        )}
      </div>
    </dl>
  );
}

function IncidentCard({ lang, incident, onReview }: {
  lang: Translation;
  incident: AdminIncident;
  onReview: (update: ReviewUpdate) => Promise<boolean>;
}) {
  const text = lang.admin;
  const [isOpen, setIsOpen] = useState(false);
  const detailsId = useId();
  const person = incident.user === null ? text.deletedAccount : personLabel(incident.user) || text.unknown;

  return (
    <li className={`${CARD} flex flex-col gap-2`}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge text={text} status={incident.status} />
        <span className="text-sm font-semibold break-all">{person}</span>
        <span className="text-xs text-muted">{formatDateTime(incident.createdAt, lang.htmlLang)}</span>
      </div>
      <p className="text-sm break-words line-clamp-2">{incident.question}</p>
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
          <IncidentDetails lang={lang} incident={incident} />
          <ReviewForm key={`${incident.status}-${incident.adminNote}`} text={text} status={incident.status} note={incident.adminNote} onSubmit={onReview} />
        </div>
      )}
    </li>
  );
}

// Prompt-injection attempts (heuristic and/or the model's marker), with the
// person who tried - for the board to review.
export default function IncidentsTab({ lang }: IncidentsTabProps) {
  const text = lang.admin;
  const [status, setStatus] = useState<ReviewStatus | null>('open');
  const [offset, setOffset] = useState(0);
  const load = useCallback(() => fetchIncidents(status, offset), [status, offset]);
  const incidents = useLoader(load);
  const { update } = incidents;

  const review = useCallback(async (id: string, change: ReviewUpdate): Promise<boolean> => {
    try {
      const saved = await reviewIncident(id, change);
      update((page) => ({ ...page, items: page.items.map((item) => (item.id === id ? saved : item)) }));
      return true;
    } catch {
      return false;
    }
  }, [update]);

  const changeStatus = (next: ReviewStatus | null) => {
    setStatus(next);
    setOffset(0);
  };

  const page = incidents.data;
  return (
    <section className="flex flex-col gap-4" aria-busy={incidents.isLoading}>
      <StatusFilter text={text} value={status} onChange={changeStatus} />

      {incidents.hasError && <LoadError text={text} retryLabel={lang.retry} onRetry={incidents.reload} />}
      {incidents.isLoading && page === null && <LoadingRow label={lang.loading} />}
      {page !== null && page.items.length === 0 && !incidents.isLoading && <p className="text-sm text-muted">{text.noIncidents}</p>}
      {page !== null && page.items.length > 0 && (
        <ul className={`flex flex-col gap-3 ${incidents.isLoading ? 'opacity-60' : ''}`}>
          {page.items.map((incident) => (
            <IncidentCard key={incident.id} lang={lang} incident={incident} onReview={(change) => review(incident.id, change)} />
          ))}
        </ul>
      )}
      {page !== null && (
        <Pagination text={text} offset={page.offset} count={page.items.length} total={page.total} pageSize={PAGE_SIZE} onOffset={setOffset} />
      )}
    </section>
  );
}
