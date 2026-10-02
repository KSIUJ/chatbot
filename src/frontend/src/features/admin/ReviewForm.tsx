import { useId, useState } from 'react';
import type { AdminTranslation } from '../preferences/languages';
import type { ReviewStatus, ReviewUpdate } from './adminApi';
import { HINT, INPUT, LABEL } from './styles';

// Same limit as the backend (MAX_ADMIN_NOTE_LENGTH).
const MAX_NOTE_LENGTH = 1000;

interface ReviewFormProps {
  text: AdminTranslation;
  status: ReviewStatus | null;
  note: string | null;
  // resolves to true once saved
  onSubmit: (update: ReviewUpdate) => Promise<boolean>;
}

// Note of the board plus the status buttons: an open item can be resolved or
// dismissed, a closed one reopened (the note is saved with each of them).
export default function ReviewForm({ text, status, note, onSubmit }: ReviewFormProps) {
  const [draft, setDraft] = useState(note ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [hasError, setHasError] = useState(false);
  const noteId = useId();
  const errorId = useId();

  const submit = async (next: ReviewStatus) => {
    if (isSaving) return;
    setIsSaving(true);
    setHasError(false);
    const saved = await onSubmit({ status: next, adminNote: draft });
    setIsSaving(false);
    setHasError(!saved);
  };

  const actions: { status: ReviewStatus; label: string; primary: boolean }[] =
    status === 'open'
      ? [
          { status: 'resolved', label: text.resolve, primary: true },
          { status: 'dismissed', label: text.dismiss, primary: false },
        ]
      : [{ status: 'open', label: text.reopen, primary: false }];

  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3">
      <label htmlFor={noteId} className={LABEL}>
        {text.adminNote}
      </label>
      <textarea
        id={noteId}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        maxLength={MAX_NOTE_LENGTH}
        rows={2}
        disabled={isSaving}
        aria-describedby={hasError ? errorId : undefined}
        className={`${INPUT} resize-y`}
      />
      <span className={`${HINT} self-end`} aria-hidden="true">
        {draft.length}/{MAX_NOTE_LENGTH}
      </span>
      {hasError && (
        <p id={errorId} role="alert" className="text-label text-danger-text">
          {text.saveError}
        </p>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        {actions.map((action) => (
          <button
            key={action.status}
            type="button"
            onClick={() => void submit(action.status)}
            disabled={isSaving}
            className={`ksi-btn ${action.primary ? 'ksi-btn-primary' : 'ksi-btn-secondary'} disabled:opacity-50`}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
