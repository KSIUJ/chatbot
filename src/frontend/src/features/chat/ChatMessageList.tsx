import { useEffect, useRef } from 'react';
import { Bot, Check, Copy, Loader2, RefreshCw } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import type { ThemeStyle } from '../preferences/themes';
import { isMarker, type ChatMessage } from './conversations';
import MessageSources from './MessageSources';

// How close to the bottom (px) still counts as "reading the latest answer".
const NEAR_BOTTOM_PX = 120;

interface ChatMessageListProps {
  t: ThemeStyle;
  lang: Translation;
  messages: ChatMessage[];
  isWaiting: boolean;
  isLoading: boolean;
  loadError: boolean;
  copiedId: string | null;
  onCopy: (message: ChatMessage) => void;
  onRetry: () => void;
  onReload: () => void;
}

function BotAvatar({ t }: { t: ThemeStyle }) {
  return (
    <div className={`h-10 w-10 ${t.botIcon} rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm mt-0.5`}>
      <Bot size={22} />
    </div>
  );
}

export default function ChatMessageList({
  t, lang, messages, isWaiting, isLoading, loadError, copiedId, onCopy, onRetry, onReload,
}: ChatMessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  // updated on scroll, so a reader who scrolled up is not pulled down
  const isNearBottomRef = useRef(true);

  const last = messages.at(-1);
  const streamingText = last?.status === 'streaming' ? last.text : null;

  // a new bubble or the typing indicator: scroll to it
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, isWaiting]);

  // the streamed answer grows (and at the end gets its sources): follow it
  // only when the reader is at the bottom
  const wasStreamingRef = useRef(false);
  useEffect(() => {
    const main = mainRef.current;
    const isStreaming = streamingText !== null;
    const justFinished = wasStreamingRef.current && !isStreaming;
    wasStreamingRef.current = isStreaming;
    if ((!isStreaming && !justFinished) || main === null || !isNearBottomRef.current) return;
    main.scrollTop = main.scrollHeight;
  }, [streamingText]);

  const handleScroll = () => {
    const main = mainRef.current;
    if (main !== null) isNearBottomRef.current = main.scrollHeight - main.scrollTop - main.clientHeight < NEAR_BOTTOM_PX;
  };

  if (isLoading) {
    return (
      <main className="flex-1 flex items-center justify-center">
        <div role="status">
          <Loader2 className={`w-6 h-6 animate-spin ${t.textMuted}`} />
          <span className="sr-only">{lang.loading}</span>
        </div>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className={`flex-1 flex flex-col items-center justify-center gap-3 ${t.text}`}>
        <p className="text-sm">{lang.loadError}</p>
        <button type="button" onClick={onReload} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm ${t.hover}`}>
          <RefreshCw size={14} />
          {lang.retry}
        </button>
      </main>
    );
  }

  const lastId = last?.id;
  // typing dots only until the first words of the answer arrive
  const showTyping = isWaiting && streamingText === null;

  return (
    <main ref={mainRef} onScroll={handleScroll} className="flex-1 p-4 pt-8 overflow-y-auto space-y-6">
      {/* empty conversation: greeting instead of a fake stored message */}
      {messages.length === 0 && !isWaiting && (
        <div className="flex gap-4 max-w-4xl mx-auto w-full">
          <BotAvatar t={t} />
          <div className={`p-5 rounded-2xl rounded-tl-sm border text-[15px] leading-relaxed max-w-[70%] ${t.msgBox}`}>
            {lang.greeting}
          </div>
        </div>
      )}

      {messages.map((msg) => {
        const isUser = msg.sender === 'user';
        const marker = isMarker(msg);
        const isStreaming = msg.status === 'streaming';
        // a stopped answer keeps the text received so far, with a note below
        const hasPartialText = msg.status === 'stopped' && msg.text !== '';
        const markerText = msg.status === 'stopped' ? lang.stopped : lang.error;
        const text = marker && !hasPartialText ? markerText : msg.text;
        const isCopied = copiedId === msg.id;
        const canCopy = !isUser && msg.status === undefined;
        const sources = !isUser && msg.status === undefined ? msg.sources ?? [] : [];

        return (
          <div key={msg.id} className={`flex gap-4 max-w-4xl mx-auto w-full ${isUser ? 'flex-row-reverse' : ''}`}>
            {!isUser && <BotAvatar t={t} />}

            <div className="flex flex-col gap-2 max-w-[70%]">
              <div
                className={`p-5 relative rounded-2xl border text-[15px] leading-relaxed whitespace-pre-wrap break-words
                  ${isUser ? `${t.userMsgBox} rounded-tr-sm` : `${t.msgBox} rounded-tl-sm`}
                  ${marker && !hasPartialText ? 'opacity-80 italic' : ''}
                  ${canCopy || isStreaming ? 'pr-14' : ''}`}
                aria-busy={isStreaming || undefined}
              >
                {text}
                {hasPartialText && <span className="block mt-2 text-sm italic opacity-80">{markerText}</span>}

                {canCopy && (
                  <button
                    type="button"
                    onClick={() => onCopy(msg)}
                    className={`absolute top-3 right-3 p-1.5 rounded-md transition-colors ${isCopied ? t.copiedIcon : `${t.textMuted} ${t.hover}`}`}
                    title={isCopied ? lang.copied : lang.copy}
                    aria-label={isCopied ? lang.copied : lang.copy}
                  >
                    {isCopied ? <Check size={16} /> : <Copy size={16} />}
                  </button>
                )}
              </div>

              {sources.length > 0 && <MessageSources t={t} lang={lang} sources={sources} />}

              {/* retry only on the latest failed / stopped answer */}
              {marker && msg.id === lastId && (
                <button
                  type="button"
                  onClick={onRetry}
                  disabled={isWaiting}
                  className={`self-start flex items-center gap-1.5 p-1.5 rounded-md text-[11px] font-bold uppercase tracking-wide ${
                    isWaiting ? 'opacity-50 cursor-not-allowed' : `${t.textMuted} ${t.hover}`
                  }`}
                >
                  <RefreshCw size={13} />
                  {lang.retry}
                </button>
              )}
            </div>
          </div>
        );
      })}

      {/* waiting for the answer */}
      {showTyping && (
        <div className="flex gap-4 max-w-4xl mx-auto w-full">
          <BotAvatar t={t} />
          <div role="status" className={`px-5 rounded-2xl rounded-tl-sm border flex items-center h-13 ${t.msgBox}`}>
            <span className="sr-only">{lang.waitingPlaceholder}</span>
            <div className="flex gap-1.5 items-center" aria-hidden="true">
              <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        </div>
      )}

      <div ref={endRef} />
    </main>
  );
}
