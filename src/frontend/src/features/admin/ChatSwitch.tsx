import { useId, useState } from 'react';
import { Power } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import { saveChatSwitch, type AdminSettings } from './adminApi';
import ConfirmDialog from './ConfirmDialog';
import { HINT, INPUT, LABEL, SECTION_TITLE } from './styles';

// Same limit as the backend (MAX_CHAT_DISABLED_MESSAGE_LENGTH).
const MAX_MESSAGE_LENGTH = 300;

interface ChatSwitchProps {
  lang: Translation;
  settings: AdminSettings;
  onSaved: (settings: AdminSettings) => void;
}

// Kill switch for the whole chat (e.g. when the model misbehaves): switching
// off asks for confirmation first and blocks questions for everyone,
// admins included; switching back on is immediate.
export default function ChatSwitch({ lang, settings, onSaved }: ChatSwitchProps) {
  const text = lang.admin;
  const [message, setMessage] = useState(settings.chatDisabledMessage ?? '');
  const [isConfirming, setIsConfirming] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [hasError, setHasError] = useState(false);
  const messageId = useId();
  const hintId = useId();
  const isOn = settings.chatEnabled;

  const save = async (enabled: boolean) => {
    setIsSaving(true);
    setHasError(false);
    try {
      onSaved(await saveChatSwitch(enabled, message));
      setIsConfirming(false);
    } catch {
      setHasError(true);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section
      aria-labelledby={`${messageId}-title`}
      className={`rounded-card border p-4 sm:p-5 flex flex-col gap-3 ${
        isOn ? 'border-line bg-surface' : 'ksi-alert-danger'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className={`size-2.5 rounded-full ${isOn ? 'bg-[var(--ksi-success)]' : 'bg-danger'}`}
          />
          <div>
            <h2 id={`${messageId}-title`} className={SECTION_TITLE}>
              {text.chatSwitch}
            </h2>
            <p role="status" className={`text-sm ${isOn ? 'text-muted' : 'text-danger-text font-semibold'}`}>
              {isOn ? text.chatIsOn : text.chatIsOff}
            </p>
          </div>
        </div>
        {isOn ? (
          <button
            type="button"
            onClick={() => setIsConfirming(true)}
            disabled={isSaving}
            className="ksi-btn bg-danger text-white hover:opacity-90 disabled:opacity-50"
          >
            <Power size={15} aria-hidden="true" />
            {text.turnOff}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void save(true)}
            disabled={isSaving}
            className="ksi-btn ksi-btn-primary disabled:opacity-50"
          >
            <Power size={15} aria-hidden="true" />
            {text.turnOn}
          </button>
        )}
      </div>

      {isOn && (
        <div className="flex flex-col gap-1">
          <label htmlFor={messageId} className={LABEL}>
            {text.disabledMessage}
          </label>
          <input
            id={messageId}
            type="text"
            value={message}
            maxLength={MAX_MESSAGE_LENGTH}
            disabled={isSaving}
            onChange={(event) => setMessage(event.target.value)}
            aria-describedby={hintId}
            className={INPUT}
          />
          <span id={hintId} className={HINT}>
            {text.disabledMessageHint}
          </span>
        </div>
      )}
      {!isOn && settings.chatDisabledMessage !== null && (
        <p className="text-sm break-words">“{settings.chatDisabledMessage}”</p>
      )}

      {hasError && (
        <p role="alert" className="text-label text-danger-text">
          {text.saveError}
        </p>
      )}

      {isConfirming && (
        <ConfirmDialog
          title={text.confirmTurnOffTitle}
          text={text.confirmTurnOffText}
          confirmLabel={text.confirmTurnOff}
          cancelLabel={lang.cancel}
          isBusy={isSaving}
          onConfirm={() => void save(false)}
          onCancel={() => setIsConfirming(false)}
        />
      )}
    </section>
  );
}
