import { useCallback, useState } from 'react';
import { LockOpen, RefreshCw, RotateCcw } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import { fetchBlocks, unblockPerson, type WarnedPerson } from './adminApi';
import { LoadError, LoadingRow } from './AdminCommon';
import ConfirmDialog from './ConfirmDialog';
import { formatDateTime, personLabel } from './format';
import { BADGE, CARD, HINT } from './styles';
import { useLoader } from './useLoader';

interface BlocksTabProps {
  lang: Translation;
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className={`${HINT} inline`}>{label}: </dt>
      <dd className="inline text-xs">{value}</dd>
    </div>
  );
}

function PersonCard({ lang, person, warningLimit, isBusy, onUnblock }: {
  lang: Translation;
  person: WarnedPerson;
  warningLimit: number;
  isBusy: boolean;
  onUnblock: () => void;
}) {
  const text = lang.admin;
  const { user } = person;
  const isBlocked = person.blockedAt !== null;

  return (
    <li className={`${CARD} flex flex-col gap-2 ${isBlocked ? 'ksi-alert-danger' : ''}`}>
      <div className="flex flex-wrap items-center gap-2">
        {isBlocked && <span className={`${BADGE} border-danger text-danger-text`}>{text.blockedBadge}</span>}
        <span className={`${BADGE} border-line-strong text-fg`}>{text.warningsCount(person.warnings, warningLimit)}</span>
        <span className="text-sm font-semibold break-all">{personLabel(user) || text.unknown}</span>
      </div>
      <div className="flex flex-col text-sm break-words">
        {user.username !== null && <span className="text-muted">{user.username}</span>}
        {user.email !== null && (
          <a href={`mailto:${user.email}`} className="ksi-link font-normal self-start">
            {user.email}
          </a>
        )}
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1">
        {isBlocked && <Detail label={text.blockedSince} value={formatDateTime(person.blockedAt, lang.htmlLang)} />}
        <Detail label={text.lastWarning} value={formatDateTime(person.lastWarningAt, lang.htmlLang)} />
        {person.warningsResetAt !== null && (
          <Detail label={text.lastReset} value={formatDateTime(person.warningsResetAt, lang.htmlLang)} />
        )}
      </dl>
      <button
        type="button"
        onClick={onUnblock}
        disabled={isBusy}
        className={`ksi-btn ${isBlocked ? 'ksi-btn-primary' : 'ksi-btn-secondary'} self-start disabled:opacity-50`}
      >
        {isBlocked ? <LockOpen size={15} aria-hidden="true" /> : <RotateCcw size={15} aria-hidden="true" />}
        {isBlocked ? text.unblock : text.resetWarnings}
      </button>
    </li>
  );
}

// People blocked after warnings for trying to get around the bot's rules, and
// people with warnings below the limit. A board member can lift a block (or
// reset the warnings) after talking to the person.
export default function BlocksTab({ lang }: BlocksTabProps) {
  const text = lang.admin;
  const blocks = useLoader(fetchBlocks);
  const { update } = blocks;
  const [pending, setPending] = useState<WarnedPerson | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [hasError, setHasError] = useState(false);

  const confirm = useCallback(async () => {
    if (pending === null) return;
    setIsSaving(true);
    setHasError(false);
    try {
      const saved = await unblockPerson(pending.user.id);
      // without warnings and a block the person leaves the list
      update((list) => ({
        ...list,
        items: list.items
          .map((item) => (item.user.id === saved.user.id ? saved : item))
          .filter((item) => item.blockedAt !== null || item.warnings > 0),
      }));
      setPending(null);
    } catch {
      setHasError(true);
      setPending(null);
    } finally {
      setIsSaving(false);
    }
  }, [pending, update]);

  const data = blocks.data;
  const isUnblock = pending?.blockedAt !== null;
  return (
    <section className="flex flex-col gap-4" aria-busy={blocks.isLoading}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        {data !== null && <p className="text-sm text-muted max-w-prose">{text.blocksIntro(data.warningLimit)}</p>}
        <button type="button" onClick={blocks.reload} disabled={blocks.isLoading} className="ksi-btn ksi-btn-secondary disabled:opacity-50">
          <RefreshCw size={14} aria-hidden="true" />
          {text.refresh}
        </button>
      </div>

      {hasError && (
        <p role="alert" className="ksi-alert-danger rounded-card p-3 text-sm text-danger-text">
          {text.saveError}
        </p>
      )}
      {blocks.hasError && <LoadError text={text} retryLabel={lang.retry} onRetry={blocks.reload} />}
      {blocks.isLoading && data === null && <LoadingRow label={lang.loading} />}
      {data !== null && data.items.length === 0 && !blocks.isLoading && <p className="text-sm text-muted">{text.noBlocks}</p>}
      {data !== null && data.items.length > 0 && (
        <ul className={`flex flex-col gap-3 ${blocks.isLoading ? 'opacity-60' : ''}`}>
          {data.items.map((person) => (
            <PersonCard
              key={person.user.id}
              lang={lang}
              person={person}
              warningLimit={data.warningLimit}
              isBusy={isSaving}
              onUnblock={() => setPending(person)}
            />
          ))}
        </ul>
      )}

      {pending !== null && (
        <ConfirmDialog
          title={isUnblock ? text.confirmUnblockTitle : text.confirmResetTitle}
          text={isUnblock ? text.confirmUnblockText : text.confirmResetText}
          confirmLabel={isUnblock ? text.unblock : text.resetWarnings}
          cancelLabel={lang.cancel}
          isBusy={isSaving}
          onConfirm={() => void confirm()}
          onCancel={() => setPending(null)}
        />
      )}
    </section>
  );
}
