import { X } from 'lucide-react';
import type { UsosTranslation } from '../preferences/languages';
import type { UsosResult } from './usos';

interface UsosNoticeProps {
  t: UsosTranslation;
  result: UsosResult;
  onDismiss: () => void;
}

// Banner over the chat after coming back from the USOS consent page.
export default function UsosNotice({ t, result, onDismiss }: UsosNoticeProps) {
  const isError = result !== 'connected';
  return (
    <div
      role={isError ? 'alert' : 'status'}
      className={`max-w-2xl mx-auto flex items-start gap-2.5 rounded-card px-4 py-2.5 text-sm ${
        isError ? 'ksi-alert-danger' : 'border border-line bg-surface'
      }`}
    >
      <p className="flex-1">{t.results[result]}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={t.dismiss}
        title={t.dismiss}
        className="shrink-0 p-0.5 rounded-control text-muted transition-colors hover:bg-surface-hover hover:text-fg"
      >
        <X size={16} />
      </button>
    </div>
  );
}
