import { useId, useState, type FormEvent } from 'react';
import type { AdminTranslation } from '../preferences/languages';
import type { AdminUser, LimitChoice, LimitMode, NumberRange } from './adminApi';
import { initialChoice, parseBounded } from './limitsForm';
import { HINT, INPUT, LABEL } from './styles';

// Same limit as the backend (admin/schemas.py MAX_NOTE_LENGTH).
const MAX_NOTE_LENGTH = 500;
const LIMIT_MODES: readonly LimitMode[] = ['global', 'custom', 'unlimited'];

interface UserLimitEditorProps {
  text: AdminTranslation;
  cancelLabel: string;
  user: AdminUser;
  globalLimit: number;
  range: NumberRange;
  // resolves to true once saved (the editor is then closed by the parent)
  onSave: (choice: LimitChoice) => Promise<boolean>;
  onCancel: () => void;
}

// Exception for one person: back to the global limit, an own daily limit
// (0 blocks) or no limit, with an optional note for other board members.
export default function UserLimitEditor({ text, cancelLabel, user, globalLimit, range, onSave, onCancel }: UserLimitEditorProps) {
  const start = initialChoice(user, globalLimit);
  const [mode, setMode] = useState<LimitMode>(start.mode);
  const [limit, setLimit] = useState(String(start.dailyLimit));
  const [note, setNote] = useState(start.note);
  const [isSaving, setIsSaving] = useState(false);
  const [hasError, setHasError] = useState(false);
  const groupName = useId();
  const limitId = useId();
  const noteId = useId();
  const parsedLimit = parseBounded(limit, range);
  const canSave = mode !== 'custom' || parsedLimit !== null;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSave || isSaving) return;
    setIsSaving(true);
    setHasError(false);
    const saved = await onSave({ mode, dailyLimit: parsedLimit ?? globalLimit, note });
    if (!saved) {
      setIsSaving(false);
      setHasError(true);
    }
  };

  return (
    <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-col gap-3 border-t border-line pt-3" noValidate>
      <fieldset className="flex flex-col gap-2" disabled={isSaving}>
        <legend className={`${LABEL} mb-1`}>{text.editLimit}</legend>
        {LIMIT_MODES.map((option) => (
          <label key={option} className="flex items-center gap-2.5 text-sm cursor-pointer">
            <input
              type="radio"
              name={groupName}
              value={option}
              checked={mode === option}
              onChange={() => setMode(option)}
              className="size-4 accent-accent"
            />
            {option === 'global' ? `${text.limitModes.global} (${globalLimit})` : text.limitModes[option]}
          </label>
        ))}
      </fieldset>

      {mode === 'custom' && (
        <div className="flex flex-col gap-1">
          <label htmlFor={limitId} className={LABEL}>
            {text.customLimit}
          </label>
          <input
            id={limitId}
            type="number"
            inputMode="numeric"
            min={range.min}
            max={range.max}
            step={1}
            value={limit}
            disabled={isSaving}
            onChange={(event) => setLimit(event.target.value)}
            aria-invalid={parsedLimit === null || undefined}
            className={`${INPUT} sm:max-w-40`}
          />
          <span className={HINT}>
            {range.min}–{range.max} · {text.blockedHint}
          </span>
        </div>
      )}

      {mode !== 'global' && (
        <div className="flex flex-col gap-1">
          <label htmlFor={noteId} className={LABEL}>
            {text.note}
          </label>
          <input
            id={noteId}
            type="text"
            value={note}
            maxLength={MAX_NOTE_LENGTH}
            disabled={isSaving}
            onChange={(event) => setNote(event.target.value)}
            className={INPUT}
          />
        </div>
      )}

      {hasError && (
        <p role="alert" className="text-label text-danger-text">
          {text.saveError}
        </p>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={onCancel} disabled={isSaving} className="ksi-btn ksi-btn-secondary">
          {cancelLabel}
        </button>
        <button type="submit" disabled={!canSave || isSaving} className="ksi-btn ksi-btn-primary disabled:opacity-50">
          {text.save}
        </button>
      </div>
    </form>
  );
}
