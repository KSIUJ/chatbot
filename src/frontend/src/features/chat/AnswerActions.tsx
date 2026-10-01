import type { ReactNode } from 'react';
import { Check, Copy, Flag, ThumbsDown, ThumbsUp } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import type { MessageFeedback, Rating } from './feedback';

interface AnswerActionsProps {
  lang: Translation;
  feedback: MessageFeedback;
  isCopied: boolean;
  hasError: boolean;
  onCopy: () => void;
  onRate: (rating: Rating) => void;
  onReport: () => void;
}

interface ActionButtonProps {
  label: string;
  isActive: boolean;
  pressed?: boolean;
  // stays focusable (aria-disabled, not disabled), so focus can return here
  // from the report dialog
  isInert?: boolean;
  onClick: () => void;
  children: ReactNode;
}

function ActionButton({ label, isActive, pressed, isInert = false, onClick, children }: ActionButtonProps) {
  return (
    <button
      type="button"
      onClick={isInert ? undefined : onClick}
      aria-pressed={pressed}
      aria-disabled={isInert || undefined}
      title={label}
      aria-label={label}
      className={`p-1.5 rounded-control transition-colors ${
        isActive ? 'text-accent bg-accent-soft' : 'text-muted hover:bg-surface-hover hover:text-fg'
      } ${isInert ? 'cursor-default' : ''}`}
    >
      {children}
    </button>
  );
}

// Toolbar under a finished bot answer: copy, thumbs up / down, report.
export default function AnswerActions({
  lang, feedback, isCopied, hasError, onCopy, onRate, onReport,
}: AnswerActionsProps) {
  const isUp = feedback.rating === 1;
  const isDown = feedback.rating === -1;

  return (
    <div className="flex flex-col gap-1">
      <div role="group" aria-label={lang.answerActions} className="flex items-center gap-0.5 -ml-1.5">
        <ActionButton label={isCopied ? lang.copied : lang.copy} isActive={isCopied} onClick={onCopy}>
          {isCopied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
        </ActionButton>
        <ActionButton label={lang.rateUp} isActive={isUp} pressed={isUp} onClick={() => onRate(1)}>
          <ThumbsUp size={16} fill={isUp ? 'currentColor' : 'none'} aria-hidden="true" />
        </ActionButton>
        <ActionButton label={lang.rateDown} isActive={isDown} pressed={isDown} onClick={() => onRate(-1)}>
          <ThumbsDown size={16} fill={isDown ? 'currentColor' : 'none'} aria-hidden="true" />
        </ActionButton>
        <ActionButton
          label={feedback.reported ? lang.reported : lang.report}
          isActive={feedback.reported}
          isInert={feedback.reported}
          onClick={onReport}
        >
          <Flag size={16} fill={feedback.reported ? 'currentColor' : 'none'} aria-hidden="true" />
        </ActionButton>
      </div>
      {hasError && (
        <p role="alert" className="text-label text-danger-text">
          {lang.feedbackError}
        </p>
      )}
    </div>
  );
}
