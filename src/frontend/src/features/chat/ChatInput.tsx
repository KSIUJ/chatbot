import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Send, Square } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import type { ThemeStyle } from '../preferences/themes';
import { MAX_MESSAGE_LENGTH } from './conversations';

const MAX_INPUT_HEIGHT_PX = 200;

interface ChatInputProps {
  t: ThemeStyle;
  lang: Translation;
  isWaiting: boolean;
  // returns false when the message was not sent (empty / busy) - text stays
  onSend: (text: string) => boolean;
  onStop: () => void;
}

export default function ChatInput({ t, lang, isWaiting, onSend, onStop }: ChatInputProps) {
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
          className={`w-full pl-5 pr-14 py-3 border shadow-md rounded-3xl focus:ring-2 outline-none transition-all duration-100 resize-none overflow-hidden ${t.inputBox}`}
        />

        {isWaiting ? (
          <button
            type="button"
            onClick={onStop}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-2.5 rounded-full transition-colors shadow-sm active:scale-95 text-neutral-400 hover:text-red-500 hover:bg-red-500/10"
            title={lang.stop}
            aria-label={lang.stop}
          >
            <Square size={18} fill="currentColor" />
          </button>
        ) : (
          <button
            type="submit"
            className={`absolute right-2 top-1/2 -translate-y-1/2 p-2.5 rounded-full transition-colors shadow-sm active:scale-95 ${t.sendBtn}`}
            title={lang.send}
            aria-label={lang.send}
          >
            <Send size={18} className="-translate-x-px translate-y-px" />
          </button>
        )}
      </div>

      <div className={`text-center text-[10px] ${t.textMuted} font-medium`}>{lang.disclaimer}</div>
    </form>
  );
}
