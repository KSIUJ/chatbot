import { useEffect, useRef } from 'react';
import { Bot, Check, Copy, Loader2, RefreshCw } from 'lucide-react';
import type { ThemeStyle } from './themes';
import type { Translation } from './languages';
import type { ChatMessage } from '../../lib/conversations';

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

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isWaiting]);

  if (isLoading) {
    return (
      <main className="flex-1 flex items-center justify-center">
        <Loader2 className={`w-6 h-6 animate-spin ${t.textMuted}`} aria-label="Loading" />
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

  const lastId = messages.at(-1)?.id;

  return (
    <main className="flex-1 p-4 pt-8 overflow-y-auto space-y-6">
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
        const isMarker = msg.status !== undefined;
        const text = msg.status === 'stopped' ? lang.stopped : msg.status === 'error' ? lang.error : msg.text;
        const isCopied = copiedId === msg.id;

        return (
          <div key={msg.id} className={`flex gap-4 max-w-4xl mx-auto w-full ${isUser ? 'flex-row-reverse' : ''}`}>
            {!isUser && <BotAvatar t={t} />}

            <div className="flex flex-col gap-2 max-w-[70%]">
              <div
                className={`p-5 relative rounded-2xl border text-[15px] leading-relaxed whitespace-pre-wrap break-words
                  ${isUser ? `${t.userMsgBox} rounded-tr-sm` : `${t.msgBox} rounded-tl-sm`}
                  ${isMarker ? 'opacity-80 italic' : ''}
                  ${!isUser && !isMarker ? 'pr-14' : ''}`}
              >
                {text}

                {!isUser && !isMarker && (
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

              {/* retry only on the latest failed / stopped answer */}
              {isMarker && msg.id === lastId && (
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
      {isWaiting && (
        <div className="flex gap-4 max-w-4xl mx-auto w-full">
          <BotAvatar t={t} />
          <div className={`px-5 rounded-2xl rounded-tl-sm border flex items-center h-13 ${t.msgBox}`}>
            <div className="flex gap-1.5 items-center">
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
