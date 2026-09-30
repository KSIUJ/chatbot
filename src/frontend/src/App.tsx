import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import ChatScreen from './features/Chat/ChatScreen';
import LoginScreen from './features/Auth/LoginScreen';
import ProfileScreen from './features/Profile/ProfileScreen';
import { useAuth } from './features/Auth/useAuth';
import { THEME_STORAGE_KEY, parseThemePreference } from './features/Chat/themes';
import { useResolvedTheme } from './features/Chat/useResolvedTheme';

type View = 'chat' | 'profile';

export default function App() {
  // session lives in an HttpOnly cookie - the backend is the only source of truth
  const { state, login, logout } = useAuth();

  // track which screen is currently visible
  const [activeView, setActiveView] = useState<View>(() =>
    localStorage.getItem('chatActiveView') === 'profile' ? 'profile' : 'chat'
  );

  // same theme preference as the chat, resolved for the profile screen
  const profileTheme = useResolvedTheme(parseThemePreference(localStorage.getItem(THEME_STORAGE_KEY)));

  // save active view to memory every time it changes
  useEffect(() => {
    localStorage.setItem('chatActiveView', activeView);
  }, [activeView]);

  const handleLogout = () => {
    setActiveView('chat');
    void logout();
  };

  // checking the session with the backend, or already redirecting to KSI login
  // (dark: variant follows the device, so there is no white flash in dark mode)
  if (state.status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-[#121212]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" aria-label="Loading" />
      </div>
    );
  }

  // only reached on login errors - no session alone redirects straight to KSI
  if (state.status === 'unauthenticated') {
    return <LoginScreen error={state.error} onLogin={login} />;
  }

  // show profile screen if selected
  if (activeView === 'profile') {
    return (
      <ProfileScreen
        user={state.user}
        onClose={() => setActiveView('chat')}
        onLogout={handleLogout}
        selectedTheme={profileTheme}
      />
    );
  }

  // default view: show main chat view
  return (
    <ChatScreen
      onOpenProfile={() => setActiveView('profile')}
      onLogout={handleLogout}
    />
  );
}
