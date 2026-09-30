import { useState } from 'react';
import { AlertCircle, ArrowRight, Loader2 } from 'lucide-react';
import LoginBackground from './LoginBackground';
import LoginHeader from './LoginHeader';
import type { LoginError } from './useAuth';

// Shown only when an automatic redirect to KSI login would not help (errors,
// loop guard) - a visitor without a session goes straight to Keycloak.
interface LoginScreenProps {
  error: LoginError | null;
  onLogin: () => void;
}

const ERROR_MESSAGES: Record<LoginError, string> = {
  login_incomplete: 'Login did not complete. Make sure cookies are enabled for this site and try again.',
  not_authenticated: 'Please log in with your KSI account.',
  session_expired: 'Your session has expired. Please log in again.',
  not_member: 'The chatbot is available to KSI members only (group Członek).',
  provider_unavailable: 'The KSI login server is unavailable. Please try again in a moment.',
  access_denied: 'Login was cancelled.',
  invalid_state: 'Login took too long or was started in another tab. Please try again.',
  login_failed: 'Login failed. Please try again.',
  forbidden_origin: 'Request was rejected. Please reload the page.',
};

export default function LoginScreen({ error, onLogin }: LoginScreenProps) {
  // the page navigates away to Keycloak, so the spinner never has to be reset
  const [isRedirecting, setIsRedirecting] = useState(false);

  const buttonLabel = error ? 'Try again' : 'Log in with KSI';

  const handleLogin = () => {
    setIsRedirecting(true);
    onLogin();
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center p-4 bg-white overflow-hidden">

      {/* background component */}
      <LoginBackground />

      {/* main login page container */}
      <div className="relative z-10 max-w-xs w-full bg-white/95 backdrop-blur-sm rounded-3xl shadow-xl p-5 space-y-5 border border-slate-100">
        <LoginHeader />

        {/* error message display */}
        {error && (
          <div role="alert" className="flex items-center gap-2 p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <p>{ERROR_MESSAGES[error]}</p>
          </div>
        )}

        <button
          type="button"
          onClick={handleLogin}
          disabled={isRedirecting}
          className="w-full group rounded-xl bg-blue-700/80 px-4 py-2.5 font-bold text-white transition-all hover:bg-blue-700 active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100 flex items-center justify-center gap-2 shadow-sm border border-transparent text-sm cursor-pointer"
        >
          {isRedirecting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin text-white/90" />
              Redirecting...
            </>
          ) : (
            <>
              {buttonLabel}
              <ArrowRight className="w-4 h-4 text-white/90 group-hover:translate-x-1.5 transition-transform" />
            </>
          )}
        </button>
      </div>

    </div>
  );
}
