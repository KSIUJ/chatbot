import { useCallback, useId, useState, type FormEvent } from 'react';
import { Search } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import { PAGE_SIZE, fetchUsers, saveUserLimit, type AdminUser, type LimitChoice, type NumberRange } from './adminApi';
import { LoadError, LoadingRow, Pagination } from './AdminCommon';
import { formatDateTime, personLabel, usageLabel } from './format';
import { BADGE, CARD, HINT, INPUT, SECTION_TITLE, SMALL_BUTTON } from './styles';
import { useLoader } from './useLoader';
import UserLimitEditor from './UserLimitEditor';

interface UserLimitsProps {
  lang: Translation;
  globalLimit: number;
  range: NumberRange;
}

function OverrideBadge({ lang, user }: { lang: Translation; user: AdminUser }) {
  const text = lang.admin;
  const { override } = user;
  if (override === null) return <span className={`${BADGE} border-line text-faint`}>{text.limitModes.global}</span>;
  const label = override.unlimited ? text.limitModes.unlimited : `${text.limitModes.custom}: ${override.dailyLimit ?? 0}`;
  return (
    <span className={`${BADGE} border-line-strong bg-accent-soft text-fg`} title={override.note ?? undefined}>
      {label}
    </span>
  );
}

function UserRow({ lang, user, globalLimit, range, isEditing, onEdit, onClose, onSave }: {
  lang: Translation;
  user: AdminUser;
  globalLimit: number;
  range: NumberRange;
  isEditing: boolean;
  onEdit: () => void;
  onClose: () => void;
  onSave: (choice: LimitChoice) => Promise<boolean>;
}) {
  const text = lang.admin;
  const editorId = useId();
  const label = personLabel(user) || user.id;
  const secondary = [user.username, user.email].filter((value): value is string => value !== null && value !== label);

  return (
    <li className="flex flex-col gap-2 py-3 border-b border-line last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-fg break-words">{label}</p>
          {secondary.length > 0 && <p className="text-xs text-muted break-all">{secondary.join(' · ')}</p>}
          <p className={HINT}>
            {text.lastLogin}: {formatDateTime(user.lastLoginAt, lang.htmlLang)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted tabular-nums">
            {text.usedToday}: <span className="font-semibold text-fg">{usageLabel(user.usedToday, user.effectiveLimit)}</span>
          </span>
          <OverrideBadge lang={lang} user={user} />
          <button
            type="button"
            onClick={isEditing ? onClose : onEdit}
            aria-expanded={isEditing}
            aria-controls={editorId}
            className={SMALL_BUTTON}
          >
            {text.editLimit}
          </button>
        </div>
      </div>
      {user.override?.note && <p className="text-xs text-muted break-words">{user.override.note}</p>}
      <div id={editorId}>
        {isEditing && (
          <UserLimitEditor
            text={text}
            cancelLabel={lang.cancel}
            user={user}
            globalLimit={globalLimit}
            range={range}
            onSave={onSave}
            onCancel={onClose}
          />
        )}
      </div>
    </li>
  );
}

// Search by name, login or e-mail; today's usage and the per-person exception.
export default function UserLimits({ lang, globalLimit, range }: UserLimitsProps) {
  const text = lang.admin;
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const searchId = useId();
  const load = useCallback(() => fetchUsers(query, offset), [query, offset]);
  const users = useLoader(load);

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setQuery(input);
    setOffset(0);
    setEditingId(null);
  };

  const save = async (user: AdminUser, choice: LimitChoice): Promise<boolean> => {
    try {
      await saveUserLimit(user.id, choice);
    } catch {
      return false;
    }
    setEditingId(null);
    users.reload();
    return true;
  };

  const page = users.data;
  return (
    <section className={`${CARD} flex flex-col gap-3`} aria-busy={users.isLoading}>
      <h2 className={SECTION_TITLE}>{text.users}</h2>
      <form role="search" onSubmit={handleSearch} className="flex gap-2">
        <label htmlFor={searchId} className="sr-only">
          {text.searchUsers}
        </label>
        <input
          id={searchId}
          type="search"
          value={input}
          maxLength={200}
          placeholder={text.searchUsers}
          onChange={(event) => setInput(event.target.value)}
          className={INPUT}
        />
        <button type="submit" className="ksi-btn ksi-btn-secondary shrink-0">
          <Search size={14} aria-hidden="true" />
          <span className="max-sm:sr-only">{text.search}</span>
        </button>
      </form>

      {users.hasError && <LoadError text={text} retryLabel={lang.retry} onRetry={users.reload} />}
      {users.isLoading && page === null && <LoadingRow label={lang.loading} />}
      {page !== null && page.items.length === 0 && !users.isLoading && <p className="text-sm text-muted">{text.noUsers}</p>}
      {page !== null && page.items.length > 0 && (
        <ul className={users.isLoading ? 'opacity-60' : ''}>
          {page.items.map((user) => (
            <UserRow
              key={user.id}
              lang={lang}
              user={user}
              globalLimit={globalLimit}
              range={range}
              isEditing={editingId === user.id}
              onEdit={() => setEditingId(user.id)}
              onClose={() => setEditingId(null)}
              onSave={(choice) => save(user, choice)}
            />
          ))}
        </ul>
      )}
      {page !== null && (
        <Pagination text={text} offset={page.offset} count={page.items.length} total={page.total} pageSize={PAGE_SIZE} onOffset={setOffset} />
      )}
    </section>
  );
}
