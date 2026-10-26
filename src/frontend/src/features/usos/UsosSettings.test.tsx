import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { translations } from '../preferences/languages';
import UsosNotice from './UsosNotice';
import UsosSettings from './UsosSettings';
import type { UsosActionError, UsosPhase } from './useUsos';
import type { UsosStatus } from './usos';

const t = translations.pl.usos;
const noop = () => {};

const notConnected: UsosStatus = {
  available: true,
  connected: false,
  needsReconnect: false,
  name: null,
  connectedAt: null,
  scopes: [],
};

const connected: UsosStatus = {
  ...notConnected,
  connected: true,
  name: 'Jan Kowalski',
  connectedAt: '2026-10-26T12:00:00Z',
  scopes: ['studies'],
};

function render(status: UsosStatus, phase: UsosPhase = 'idle', error: UsosActionError | null = null): string {
  return renderToStaticMarkup(
    <UsosSettings
      t={t}
      cancelLabel={translations.pl.cancel}
      locale="pl"
      status={status}
      phase={phase}
      error={error}
      onConnect={noop}
      onAskDisconnect={noop}
      onCancelDisconnect={noop}
      onDisconnect={noop}
    />,
  );
}

describe('UsosSettings', () => {
  it('shows the consent text and the connect button before linking', () => {
    const html = render(notConnected);

    expect(html).toContain(t.notConnected);
    expect(html).toContain(t.consentIntro);
    for (const item of t.consentData) expect(html).toContain(item);
    expect(html).toContain('Anthropic');
    expect(html).toContain('>Połącz z USOS</button>');
    expect(html).not.toContain(t.disconnect);
  });

  it('shows who is connected and since when, with a disconnect button', () => {
    const html = render(connected);

    expect(html).toContain('Połączono jako Jan Kowalski');
    expect(html).toContain('2026');
    expect(html).toContain(`>${t.disconnect}</button>`);
    expect(html).not.toContain(t.consentIntro);
  });

  it('asks before disconnecting', () => {
    const html = render(connected, 'confirmDisconnect');

    expect(html).toContain(t.confirmDisconnect);
    expect(html).toContain('>Anuluj</button>');
    expect(html).not.toContain('disabled=""');

    const busy = render(connected, 'disconnecting');
    expect(busy).toContain(t.disconnecting);
    expect(busy).toContain('disabled=""');
  });

  it('offers to connect again after USOS rejected the token', () => {
    const html = render({ ...connected, connected: false, needsReconnect: true });

    expect(html).toContain(t.needsReconnect);
    expect(html).toContain(`>${t.reconnect}</button>`);
    expect(html).toContain(`>${t.disconnect}</button>`);
  });

  it('only allows removing the link while the feature is switched off', () => {
    const html = render({ ...connected, available: false });

    expect(html).toContain(t.switchedOff);
    expect(html).not.toContain(t.connect);
    expect(html).toContain(`>${t.disconnect}</button>`);
  });

  it('disables the button while redirecting and shows errors', () => {
    const redirecting = render(notConnected, 'connecting');
    expect(redirecting).toContain(`>${t.connecting}</button>`);
    expect(redirecting).toContain('disabled=""');
    expect(render(notConnected, 'idle', 'connect')).toContain(t.connectError);
    expect(render(connected, 'idle', 'disconnect')).toContain(t.disconnectError);
  });
});

describe('UsosNotice', () => {
  it('announces success as a status and errors as an alert', () => {
    const ok = renderToStaticMarkup(<UsosNotice t={t} result="connected" onDismiss={noop} />);
    expect(ok).toContain('role="status"');
    expect(ok).toContain(t.results.connected);

    const error = renderToStaticMarkup(<UsosNotice t={t} result="denied" onDismiss={noop} />);
    expect(error).toContain('role="alert"');
    expect(error).toContain(t.results.denied);
    expect(error).toContain(`aria-label="${t.dismiss}"`);
  });
});
