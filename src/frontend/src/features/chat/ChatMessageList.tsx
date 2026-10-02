import { useEffect, useRef, useState } from 'react';
import { Bot, Loader2, RefreshCw } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import AnswerActions from './AnswerActions';
import { isMarker, type ChatMessage } from './conversations';
import { EMPTY_FEEDBACK, canGiveFeedback, type Rating, type ReportReason } from './feedback';
import MessageSources from './MessageSources';
import ReportDialog from './ReportDialog';
import { formatResetTime } from './usage';

// How close to the bottom (px) still counts as "reading the latest answer".
const NEAR_BOTTOM_PX = 120;

interface ChatMessageListProps {
  lang: Translation;
  messages: ChatMessage[];
  isWaiting: boolean;
  isLoading: boolean;
  loadError: boolean;
  copiedId: string | null;
  feedbackErrorId: string | null;
  onCopy: (message: ChatMessage) => void;
  onRate: (message: ChatMessage, rating: Rating) => void;
  // resolves to true once the report is saved
  onReport: (message: ChatMessage, reason: ReportReason, comment: string | null) => Promise<boolean>;
  onRetry: () => void;
  onReload: () => void;
}

// Flat bubbles with a hairline border, like the KSI login card. The bot's text
// colour is set per use (regular answers, markers and typing dots differ).
const BOT_BUBBLE = 'bg-surface border border-line';
const USER_BUBBLE = 'bg-user border border-user-line text-user-fg';

function BotAvatar() {
  return (
    <div className="h-9 w-9 shrink-0 mt-0.5 flex items-center justify-center rounded-card border border-line bg-surface text-fg shadow-ksi">
      <Bot size={20} aria-hidden="true" />
    </div>
  );
}

export default function ChatMessageList({
  lang, messages, isWaiting, isLoading, loadError, copiedId, feedbackErrorId, onCopy, onRate, onReport, onRetry, onReload,
}: ChatMessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  // updated on scroll, so a reader who scrolled up is not pulled down
  const isNearBottomRef = useRef(true);
  // answer whose report dialog is open
  const [reportingId, setReportingId] = useState<string | null>(null);

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
          <Loader2 className="w-6 h-6 animate-spin text-muted" />
          <span className="sr-only">{lang.loading}</span>
        </div>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="flex-1 flex flex-col items-center justify-center gap-3 text-fg">
        <p className="text-sm">{lang.loadError}</p>
        <button type="button" onClick={onReload} className="ksi-btn ksi-btn-secondary">
          <RefreshCw size={14} aria-hidden="true" />
          {lang.retry}
        </button>
      </main>
    );
  }

  const lastId = last?.id;
  // gone after a switch to another conversation - the dialog closes with it
  const reportingMessage = reportingId === null ? undefined : messages.find((m) => m.id === reportingId);
  // typing dots only until the first words of the answer arrive
  const showTyping = isWaiting && streamingText === null;

  return (
    <main ref={mainRef} onScroll={handleScroll} className="flex-1 p-4 pt-8 overflow-y-auto space-y-6">
      {/* empty conversation: greeting instead of a fake stored message */}
      {messages.length === 0 && !isWaiting && (
        <div className="flex gap-4 max-w-4xl mx-auto w-full">
          <BotAvatar />
          <div className={`px-4 py-3 rounded-card text-sm leading-relaxed max-w-[70%] text-fg ${BOT_BUBBLE}`}>
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
        const markerText = msg.rateLimit
          ? lang.rateLimited(msg.rateLimit.limit, formatResetTime(msg.rateLimit.resetAt, lang.htmlLang))
          : msg.status === 'stopped' ? lang.stopped : lang.error;
        const text = marker && !hasPartialText ? markerText : msg.text;
        const hasActions = canGiveFeedback(msg);
        const sources = !isUser && msg.status === undefined ? msg.sources ?? [] : [];

        return (
          <div key={msg.id} className={`flex gap-4 max-w-4xl mx-auto w-full ${isUser ? 'flex-row-reverse' : ''}`}>
            {!isUser && <BotAvatar />}

            <div className="flex flex-col gap-2 max-w-[70%]">
              <div
                className={`px-4 py-3 relative rounded-card text-sm leading-relaxed whitespace-pre-wrap break-words
                  ${isUser ? USER_BUBBLE : BOT_BUBBLE}
                  ${isUser ? '' : msg.rateLimit ? 'text-fg' : marker && !hasPartialText ? 'italic text-muted' : 'text-fg'}`}
                aria-busy={isStreaming || undefined}
                role={msg.rateLimit ? 'alert' : undefined}
              >
                {text}
                {hasPartialText && <span className="block mt-2 text-label italic text-muted">{markerText}</span>}
              </div>

              {sources.length > 0 && <MessageSources lang={lang} sources={sources} />}

              {hasActions && (
                <AnswerActions
                  lang={lang}
                  feedback={msg.feedback ?? EMPTY_FEEDBACK}
                  isCopied={copiedId === msg.id}
                  hasError={feedbackErrorId === msg.id}
                  onCopy={() => onCopy(msg)}
                  onRate={(rating) => onRate(msg, rating)}
                  onReport={() => setReportingId(msg.id)}
                />
              )}

              {/* retry only on the latest failed / stopped answer - not after
                  the daily limit, it would be refused again until the reset */}
              {marker && !msg.rateLimit && msg.id === lastId && (
                <button
                  type="button"
                  onClick={onRetry}
                  disabled={isWaiting}
                  className={`self-start flex items-center gap-1.5 px-1.5 py-1 rounded-control text-[11px] font-semibold uppercase tracking-[0.04em] text-muted transition-colors ${
                    isWaiting ? 'opacity-50 cursor-not-allowed' : 'hover:bg-surface-hover hover:text-fg'
                  }`}
                >
                  <RefreshCw size={13} aria-hidden="true" />
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
          <BotAvatar />
          <div role="status" className={`px-4 rounded-card flex items-center h-11 text-muted ${BOT_BUBBLE}`}>
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

      {reportingMessage !== undefined && (
        <ReportDialog
          lang={lang}
          onSubmit={(reason, comment) => onReport(reportingMessage, reason, comment)}
          onClose={() => setReportingId(null)}
        />
      )}
    </main>
  );
}
