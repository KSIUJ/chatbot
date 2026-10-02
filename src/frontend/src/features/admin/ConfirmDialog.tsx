import { useEffect, useId, useRef, type MouseEvent, type SyntheticEvent } from 'react';

interface ConfirmDialogProps {
  title: string;
  text: string;
  confirmLabel: string;
  cancelLabel: string;
  isBusy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

// Native modal <dialog> (like the report dialog): the rest of the page is
// inert, Escape cancels, focus returns to the opener. Cancel gets the initial
// focus, so a stray Enter does not confirm a destructive action.
export default function ConfirmDialog({ title, text, confirmLabel, cancelLabel, isBusy, onConfirm, onCancel }: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const textId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    cancelRef.current?.focus();
    return () => {
      if (dialog.open) dialog.close();
      opener?.focus();
    };
  }, []);

  const requestCancel = () => {
    if (!isBusy) onCancel();
  };

  const handleCancelEvent = (event: SyntheticEvent<HTMLDialogElement>) => {
    event.preventDefault();
    requestCancel();
  };

  const handleBackdropClick = (event: MouseEvent<HTMLDialogElement>) => {
    if (event.target === event.currentTarget) requestCancel();
  };

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={textId}
      onCancel={handleCancelEvent}
      onClick={handleBackdropClick}
      className="m-auto w-[min(26rem,calc(100vw-2rem))] rounded-card border border-line bg-surface p-0 text-fg shadow-raised backdrop:bg-backdrop"
    >
      <div className="flex flex-col gap-4 p-5">
        <h2 id={titleId} className="font-head text-title font-semibold">
          {title}
        </h2>
        <p id={textId} className="text-sm">
          {text}
        </p>
        <div className="flex justify-end gap-2">
          <button ref={cancelRef} type="button" onClick={requestCancel} disabled={isBusy} className="ksi-btn ksi-btn-secondary">
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isBusy}
            className="ksi-btn bg-danger text-white hover:opacity-90 disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
