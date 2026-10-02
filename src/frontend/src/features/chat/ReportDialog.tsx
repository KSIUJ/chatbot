import { useEffect, useId, useRef, useState, type FormEvent, type MouseEvent, type SyntheticEvent } from 'react';
import type { Translation } from '../preferences/languages';
import { MAX_REPORT_COMMENT_LENGTH, REPORT_REASONS, type ReportReason } from './feedback';

interface ReportDialogProps {
  lang: Translation;
  // resolves to true once the report is saved
  onSubmit: (reason: ReportReason, comment: string | null) => Promise<boolean>;
  onClose: () => void;
}

// Report form in a native modal <dialog>: showModal() makes the rest of the
// page inert (focus stays inside), Escape closes it and focus goes back to
// the element that opened it.
export default function ReportDialog({ lang, onSubmit, onClose }: ReportDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [comment, setComment] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [hasError, setHasError] = useState(false);
  const titleId = useId();
  const commentId = useId();
  const errorId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      opener?.focus();
    };
  }, []);

  const requestClose = () => {
    if (!isSending) onClose();
  };

  // Escape: the parent unmounts the dialog (instead of the browser closing it)
  const handleCancel = (event: SyntheticEvent<HTMLDialogElement>) => {
    event.preventDefault();
    requestClose();
  };

  // Closed by the browser itself (e.g. a repeated Escape). The close event is
  // queued, so a stale one (StrictMode re-running the effect) finds the
  // dialog open again and is ignored.
  const handleNativeClose = () => {
    if (dialogRef.current?.open !== true) onClose();
  };

  // a click on the backdrop lands on the <dialog> itself, not on its content
  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === event.currentTarget) requestClose();
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (reason === null || isSending) return;
    setIsSending(true);
    setHasError(false);
    const text = comment.trim();
    const saved = await onSubmit(reason, text === '' ? null : text);
    if (saved) {
      onClose();
      return;
    }
    setIsSending(false);
    setHasError(true);
  };

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onCancel={handleCancel}
      onClose={handleNativeClose}
      onClick={handleBackdropClick}
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-card border border-line bg-surface p-0 text-fg shadow-raised backdrop:bg-backdrop"
    >
      <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-col gap-4 p-5">
        <h2 id={titleId} className="font-head text-title font-semibold">
          {lang.reportTitle}
        </h2>

        <fieldset className="flex flex-col gap-2" disabled={isSending}>
          <legend className="mb-2 text-sm font-semibold">{lang.reportReasonLabel}</legend>
          {REPORT_REASONS.map((option) => (
            <label key={option} className="flex items-center gap-2.5 text-sm cursor-pointer">
              <input
                type="radio"
                name="report-reason"
                value={option}
                checked={reason === option}
                onChange={() => setReason(option)}
                className="size-4 accent-accent"
              />
              {lang.reportReasons[option]}
            </label>
          ))}
        </fieldset>

        <div className="flex flex-col gap-1.5">
          <label htmlFor={commentId} className="text-sm font-semibold">
            {lang.reportComment}
          </label>
          <textarea
            id={commentId}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            maxLength={MAX_REPORT_COMMENT_LENGTH}
            rows={3}
            disabled={isSending}
            aria-describedby={hasError ? errorId : undefined}
            className="w-full resize-y rounded-control border border-line-strong bg-surface px-3 py-2 text-sm text-fg focus:outline-none focus-visible:shadow-ring"
          />
          <span className="self-end text-xs text-muted" aria-hidden="true">
            {comment.length}/{MAX_REPORT_COMMENT_LENGTH}
          </span>
        </div>

        {hasError && (
          <p id={errorId} role="alert" className="text-label text-danger-text">
            {lang.reportError}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button type="button" onClick={requestClose} disabled={isSending} className="ksi-btn ksi-btn-secondary">
            {lang.cancel}
          </button>
          <button
            type="submit"
            disabled={reason === null || isSending}
            className="ksi-btn ksi-btn-primary disabled:opacity-50"
          >
            {lang.reportSubmit}
          </button>
        </div>
      </form>
    </dialog>
  );
}
