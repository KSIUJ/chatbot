import { useState, type CSSProperties } from 'react';
import { AlertCircle, ArrowRight, Loader2 } from 'lucide-react';
import facadeImage from '../../assets/facade.svg';
import ksiLogo from '../../assets/logo-ksi.svg';
import type { Translation } from '../preferences/languages';
import type { LoginError } from './redirect';

// The faculty facade, painted in the background color through the SVG as a mask.
const FACADE_MASK: CSSProperties = {
  WebkitMaskImage: `url(${facadeImage})`,
  WebkitMaskSize: 'contain',
  WebkitMaskRepeat: 'no-repeat',
  WebkitMaskPosition: 'center',
  maskImage: `url(${facadeImage})`,
  maskSize: 'contain',
  maskRepeat: 'no-repeat',
  maskPosition: 'center',
};

// Shown only when an automatic redirect to KSI login would not help (errors,
// loop guard) - a visitor without a session goes straight to Keycloak.
interface LoginScreenProps {
  lang: Translation;
  error: LoginError | null;
  onLogin: () => void;
}

export default function LoginScreen({ lang, error, onLogin }: LoginScreenProps) {
  // the page navigates away to Keycloak, so the spinner never has to be reset
  const [isRedirecting, setIsRedirecting] = useState(false);

  const handleLogin = () => {
    setIsRedirecting(true);
    onLogin();
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center p-4 bg-white overflow-hidden">
      {/* decorative background, aspect ratio of facade.svg */}
      <div
        aria-hidden="true"
        className="absolute top-1/2 left-0 w-full aspect-[1536/365.5] -translate-y-1/2 opacity-30 pointer-events-none select-none bg-blue-900"
        style={FACADE_MASK}
      />

      <div className="relative z-10 max-w-xs w-full bg-white/95 backdrop-blur-sm rounded-3xl shadow-xl p-5 space-y-5 border border-slate-100">
        <div className="text-center space-y-1">
          <a
            href="https://ksi.sh"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block hover:opacity-80 transition-opacity cursor-pointer"
            title={lang.ksiWebsite}
          >
            <img src={ksiLogo} alt="KSI" className="h-16 w-auto mx-auto mb-4 object-contain" />
          </a>
          <h1 className="text-2xl font-black text-slate-900 tracking-normal">{lang.appTitle}</h1>
          <p className="text-xs font-semibold text-slate-400/80 tracking-widest uppercase">{lang.authorization}</p>
        </div>

        {error && (
          <div
            role="alert"
            className="flex items-center gap-2 p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl"
          >
            <AlertCircle className="w-4 h-4 shrink-0" />
            <p>{lang.loginErrors[error]}</p>
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
              {lang.redirecting}
            </>
          ) : (
            <>
              {error ? lang.tryAgain : lang.logIn}
              <ArrowRight className="w-4 h-4 text-white/90 group-hover:translate-x-1.5 transition-transform" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}
