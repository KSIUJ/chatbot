import { useEffect, useRef, useState, type ChangeEvent, type ClipboardEvent, type FormEvent, type KeyboardEvent } from 'react';
import { AlertCircle, Paperclip, PowerOff, SendHorizontal, Square, X } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import { PendingChips } from './AttachmentChips';
import { acceptList, type AttachmentMeta } from './attachments';
import { describeAttachmentProblem } from './attachmentText';
import { MAX_MESSAGE_LENGTH } from './conversations';
import type { AttachmentsController } from './useAttachments';

const MAX_INPUT_HEIGHT_PX = 200;

interface ChatInputProps {
  lang: Translation;
  isWaiting: boolean;
  // returns false when the message was not sent (empty / busy) - text stays
  onSend: (text: string, attachments: readonly AttachmentMeta[]) => boolean;
  onStop: () => void;
  // set while the admins have the chat switched off: banner instead of sending
  offNotice: string | null;
  attachments: AttachmentsController;
  // files sent earlier in this conversation (the server adds them to every question)
  earlierFiles: number;
}

export default function ChatInput({
  lang, isWaiting, onSend, onStop, offNotice, attachments, earlierFiles,
}: ChatInputProps) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { limits } = attachments;

  // grow with the content up to MAX_INPUT_HEIGHT_PX
  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = '0px';
    input.style.height = text === '' ? 'auto' : `${input.scrollHeight}px`;
  }, [text]);

  // give focus back once the answer arrived
  useEffect(() => {
    if (!isWaiting) inputRef.current?.focus();
  }, [isWaiting]);

  const isOff = offNotice !== null;
  // files still uploading: the question waits for them
  const isBlocked = attachments.isUploading;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isBlocked) return;
    if (onSend(text, attachments.ready)) {
      setText('');
      attachments.clearSent();
    }
  };

  // Enter sends, Shift+Enter adds a new line; Enter that confirms an IME
  // composition (e.g. accented characters) must not send
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  };

  // pasted files (e.g. a screenshot) are attached; pasted text works as usual
  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    if (limits === null || isOff) return;
    const files = Array.from(event.clipboardData.files);
    if (files.length === 0) return;
    event.preventDefault();
    attachments.addFiles(files);
  };

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    attachments.addFiles(Array.from(event.target.files ?? []));
    // the same file can be picked again after removing it
    event.target.value = '';
  };

  const placeholder = isWaiting ? lang.waitingPlaceholder : lang.inputPlaceholder;
  const canAttach = limits !== null && !isOff;

  return (
    <form onSubmit={handleSubmit} className="px-4 pb-8 z-20">
      {isOff && (
        <div role="status" className="ksi-alert-danger rounded-card max-w-2xl mx-auto mb-3 flex gap-2.5 px-4 py-3 text-sm">
          <PowerOff size={16} className="shrink-0 mt-0.5 text-danger-text" aria-hidden="true" />
          <div>
            <p className="font-semibold text-danger-text">{lang.chatOffTitle}</p>
            <p className="text-fg break-words">{offNotice}</p>
          </div>
        </div>
      )}

      <div className="max-w-2xl mx-auto">
        {attachments.problems.length > 0 && (
          <div role="alert" className="ksi-alert-danger rounded-card mb-2 flex gap-2 px-3 py-2 text-xs">
            <AlertCircle size={14} className="shrink-0 mt-0.5 text-danger-text" aria-hidden="true" />
            <ul className="flex-1 min-w-0 space-y-0.5 text-fg break-words">
              {attachments.problems.map((problem, index) => (
                <li key={`${index}-${problem.code}`}>{describeAttachmentProblem(problem, lang)}</li>
              ))}
            </ul>
            <button
              type="button"
              onClick={attachments.dismissProblems}
              className="shrink-0 self-start p-0.5 rounded-control text-muted hover:bg-surface-hover hover:text-fg"
              title={lang.attachments.dismiss}
              aria-label={lang.attachments.dismiss}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        )}
        <PendingChips lang={lang} items={attachments.items} onRemove={attachments.remove} />
        {earlierFiles > 0 && (
          <p className="mb-1.5 flex items-center gap-1.5 text-[11px] text-muted">
            <Paperclip size={12} className="shrink-0" aria-hidden="true" />
            {lang.attachments.earlierNote(earlierFiles)}
          </p>
        )}
      </div>

      <div className="max-w-2xl mx-auto relative mb-4">
        {canAttach && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              accept={acceptList(limits)}
              onChange={handleFiles}
              tabIndex={-1}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="absolute left-2 top-1/2 -translate-y-1/2 ksi-btn ksi-btn-secondary size-9 min-h-0 p-0"
              title={lang.attachments.attach}
              aria-label={lang.attachments.attach}
            >
              <Paperclip size={16} aria-hidden="true" />
            </button>
          </>
        )}
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={placeholder}
          aria-label={lang.inputPlaceholder}
          rows={1}
          disabled={isOff && !isWaiting}
          maxLength={MAX_MESSAGE_LENGTH}
          style={{ maxHeight: `${MAX_INPUT_HEIGHT_PX}px` }}
          className={`block w-full disabled:opacity-60 disabled:cursor-not-allowed ${canAttach ? 'pl-13' : 'pl-4'} pr-14 py-3 rounded-control border border-line-strong bg-surface text-sm leading-normal text-fg placeholder:text-muted outline-none resize-none overflow-hidden transition-[border-color,box-shadow] duration-[120ms] hover:border-faint focus:border-accent focus:shadow-ring`}
        />

        {isWaiting ? (
          <button
            type="button"
            onClick={onStop}
            className="absolute right-2 top-1/2 -translate-y-1/2 ksi-btn ksi-btn-secondary size-9 min-h-0 p-0 hover:text-danger"
            title={lang.stop}
            aria-label={lang.stop}
          >
            <Square size={14} fill="currentColor" aria-hidden="true" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={isOff || isBlocked}
            className="absolute right-2 top-1/2 -translate-y-1/2 ksi-btn ksi-btn-primary size-9 min-h-0 p-0 disabled:opacity-50"
            title={isBlocked ? lang.attachments.waitForUploads : lang.send}
            aria-label={isBlocked ? lang.attachments.waitForUploads : lang.send}
          >
            <SendHorizontal size={18} aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="text-center text-[11px] text-muted">{lang.disclaimer}</div>
    </form>
  );
}
