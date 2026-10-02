import { Loader2 } from 'lucide-react';
import ChatScreen from './features/chat/ChatScreen';
import LoginScreen from './features/auth/LoginScreen';
import { useAuth } from './features/auth/useAuth';
import { isDarkTheme } from './features/preferences/themes';
import { usePreferences } from './features/preferences/usePreferences';

export default function App() {
  const preferences = usePreferences();
  // the session lives in an HttpOnly cookie - the backend is the only source of truth
  const { state, login, logout } = useAuth(preferences.lang.htmlLang);

  // checking the session with the backend, or already redirecting to KSI login
  if (state.status === 'loading') {
    return (
      <div
        role="status"
        className={`min-h-screen flex items-center justify-center ${isDarkTheme(preferences.theme) ? 'bg-[#121212]' : 'bg-white'}`}
      >
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        <span className="sr-only">{preferences.lang.loading}</span>
      </div>
    );
  }

  // only reached on login errors - no session alone redirects straight to KSI
  if (state.status === 'unauthenticated') {
    return <LoginScreen lang={preferences.lang} error={state.error} onLogin={login} />;
  }

  return <ChatScreen user={state.user} preferences={preferences} onLogout={() => void logout()} />;
}
