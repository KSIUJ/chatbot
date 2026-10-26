import type { HtmlLang, UsosTranslation } from '../preferences/languages';
import type { UsosActionError, UsosPhase } from './useUsos';
import { formatConnectedAt, type UsosStatus } from './usos';

interface UsosSettingsProps {
  t: UsosTranslation;
  // "cancel" of the shared strings
  cancelLabel: string;
  locale: HtmlLang;
  status: UsosStatus;
  phase: UsosPhase;
  error: UsosActionError | null;
  onConnect: () => void;
  onAskDisconnect: () => void;
  onCancelDisconnect: () => void;
  onDisconnect: () => void;
}

// Body of the "USOS" settings submenu: the link status, the consent text and
// "connect" before linking, "disconnect" (with an inline confirmation) after.
export default function UsosSettings({
  t,
  cancelLabel,
  locale,
  status,
  phase,
  error,
  onConnect,
  onAskDisconnect,
  onCancelDisconnect,
  onDisconnect,
}: UsosSettingsProps) {
  const hasLink = status.connected || status.needsReconnect;
  const canConnect = status.available && !status.connected;
  const isBusy = phase === 'connecting' || phase === 'disconnecting';

  return (
    <div className="flex flex-col gap-2.5 px-3.5 pb-1.5 text-sm">
      {status.connected && (
        <p>
          <span className="font-semibold">{status.name ? t.connectedAs(status.name) : t.connectedUnnamed}</span>
          {status.connectedAt && (
            <span className="text-muted"> {t.connectedSince(formatConnectedAt(status.connectedAt, locale))}</span>
          )}
        </p>
      )}
      {status.needsReconnect && <p className="text-danger-text">{t.needsReconnect}</p>}
      {!hasLink && <p className="text-muted">{t.notConnected}</p>}
      {!status.available && hasLink && <p className="text-xs text-muted">{t.switchedOff}</p>}

      {canConnect && (
        <div className="flex flex-col gap-1.5 text-xs">
          <p>{t.consentIntro}</p>
          <ul className="list-disc pl-4">
            {t.consentData.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <ul className="flex flex-col gap-1 text-muted">
            {t.consentNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <button type="button" onClick={onConnect} disabled={isBusy} className="ksi-btn ksi-btn-primary mt-1 w-full">
            {phase === 'connecting' ? t.connecting : status.needsReconnect ? t.reconnect : t.connect}
          </button>
        </div>
      )}

      {hasLink && phase !== 'confirmDisconnect' && phase !== 'disconnecting' && (
        <button type="button" onClick={onAskDisconnect} disabled={isBusy} className="ksi-btn ksi-btn-secondary w-full">
          {t.disconnect}
        </button>
      )}

      {hasLink && (phase === 'confirmDisconnect' || phase === 'disconnecting') && (
        <div role="group" aria-label={t.disconnect} className="flex flex-col gap-2 rounded-control border border-line p-2.5">
          <p className="text-xs">{t.confirmDisconnect}</p>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancelDisconnect}
              disabled={phase === 'disconnecting'}
              className="ksi-btn ksi-btn-secondary"
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              onClick={onDisconnect}
              disabled={phase === 'disconnecting'}
              className="ksi-btn bg-danger text-white hover:opacity-90 disabled:opacity-50"
            >
              {phase === 'disconnecting' ? t.disconnecting : t.disconnect}
            </button>
          </div>
        </div>
      )}

      {error !== null && (
        <p role="alert" className="text-xs text-danger-text">
          {error === 'connect' ? t.connectError : t.disconnectError}
        </p>
      )}
    </div>
  );
}
