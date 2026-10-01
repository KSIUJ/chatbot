import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { SendHorizontal, Square } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import { MAX_MESSAGE_LENGTH } from './conversations';

const MAX_INPUT_HEIGHT_PX = 200;

interface ChatInputProps {
  lang: Translation;
  isWaiting: boolean;
  // returns false when the message was not sent (empty / busy) - text stays
  onSend: (text: string) => boolean;
  onStop: () => void;
}

export default function ChatInput({ lang, isWaiting, onSend, onStop }: ChatInputProps) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

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

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (onSend(text)) setText('');
  };

  // Enter sends, Shift+Enter adds a new line; Enter that confirms an IME
  // composition (e.g. accented characters) must not send
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  };

  const placeholder = isWaiting ? lang.waitingPlaceholder : lang.inputPlaceholder;

  return (
    <form onSubmit={handleSubmit} className="px-4 pb-8 z-20">
      <div className="max-w-2xl mx-auto relative mb-4">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label={lang.inputPlaceholder}
          rows={1}
          maxLength={MAX_MESSAGE_LENGTH}
          style={{ maxHeight: `${MAX_INPUT_HEIGHT_PX}px` }}
          className="block w-full pl-4 pr-14 py-3 rounded-control border border-line-strong bg-surface text-sm leading-normal text-fg placeholder:text-muted outline-none resize-none overflow-hidden transition-[border-color,box-shadow] duration-[120ms] hover:border-faint focus:border-accent focus:shadow-ring"
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
            className="absolute right-2 top-1/2 -translate-y-1/2 ksi-btn ksi-btn-primary size-9 min-h-0 p-0"
            title={lang.send}
            aria-label={lang.send}
          >
            <SendHorizontal size={18} aria-hidden="true" />
          </button>
        )}
      </div>

      <div className="text-center text-[11px] text-muted">{lang.disclaimer}</div>
    </form>
  );
}
