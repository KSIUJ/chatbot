import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import type { LoginError, LoginOptions } from './redirect';

// Shown under the title like on auth.ksi.sh - a proper name, not translated.
const KSI_NAME = 'Koło Studentów Informatyki UJ';

// Shown only when an automatic redirect to KSI login would not help (errors,
// loop guard) - a visitor without a session goes straight to Keycloak.
// Built to look exactly like the KSI Keycloak login card.
interface LoginScreenProps {
  lang: Translation;
  error: LoginError | null;
  onLogin: (options?: LoginOptions) => void;
}

type PendingAction = 'login' | 'another-account' | null;

// Keycloak's danger icon: a filled circle with the exclamation mark cut out.
function DangerIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" className="mt-0.5 mr-2 text-danger">
      <circle cx="8" cy="8" r="8" fill="currentColor" />
      <path d="M8 4.25v4.5" stroke="var(--ksi-surface)" strokeWidth="2" strokeLinecap="round" />
      <circle cx="8" cy="11.6" r="1.15" fill="var(--ksi-surface)" />
    </svg>
  );
}

function Redirecting({ label }: { label: string }) {
  return (
    <>
      <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
      {label}
    </>
  );
}

export default function LoginScreen({ lang, error, onLogin }: LoginScreenProps) {
  // the page navigates away to Keycloak, so this never has to be reset
  const [pending, setPending] = useState<PendingAction>(null);
  // logged in to KSI, but not in the member group: SSO would bring back the
  // same account, so offer the Keycloak login form for a different one
  const canSwitchAccount = error === 'not_member';

  const start = (action: Exclude<PendingAction, null>) => {
    setPending(action);
    onLogin({ forceLogin: action === 'another-account' });
  };

  return (
    <div className="relative min-h-dvh flex flex-col items-center bg-page text-fg px-4 py-[clamp(1.5rem,5vh,3rem)] max-[24rem]:px-3">
      <div className="ksi-facade" aria-hidden="true" />

      <main className="relative z-[1] my-auto w-full max-w-[25.5rem] overflow-hidden rounded-card border border-line bg-surface shadow-raised">
        <header className="flex flex-col items-center px-6 pt-7 pb-4 text-center max-[30rem]:px-[1.125rem]">
          <a href="https://ksi.sh" target="_blank" rel="noopener noreferrer" title={lang.ksiWebsite} className="mb-3.5 rounded-full">
            <span role="img" aria-label="KSI" className="ksi-logo block size-15" />
          </a>
          <h1 className="font-head text-title font-semibold tracking-[-0.005em] text-fg">{lang.appTitle}</h1>
          <p lang="pl" className="mt-1 text-xs font-medium uppercase tracking-[0.06em] text-muted">
            {KSI_NAME}
          </p>
        </header>

        <div className="px-6 pt-3 pb-6 max-[30rem]:px-[1.125rem]">
          {error && (
            <div role="alert" className="ksi-alert-danger mb-4 flex items-start rounded-control px-3 py-2 text-label">
              <DangerIcon />
              <p className="flex-1 text-danger-text">{lang.loginErrors[error]}</p>
            </div>
          )}

          <div className="flex flex-col gap-2.5 pt-1 md:gap-4">
            <button
              type="button"
              onClick={() => start('login')}
              disabled={pending !== null}
              className="ksi-btn ksi-btn-primary w-full"
            >
              {pending === 'login' ? <Redirecting label={lang.redirecting} /> : error ? lang.tryAgain : lang.logIn}
            </button>

            {canSwitchAccount && (
              <button
                type="button"
                onClick={() => start('another-account')}
                disabled={pending !== null}
                className="ksi-btn ksi-btn-secondary w-full"
              >
                {pending === 'another-account' ? <Redirecting label={lang.redirecting} /> : lang.logInAnotherAccount}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
