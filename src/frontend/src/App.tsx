import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import ChatScreen from './features/Chat/ChatScreen';
import LoginScreen from './features/Auth/LoginScreen';
import ProfileScreen from './features/Profile/ProfileScreen';
import { useAuth } from './features/Auth/useAuth';

type View = 'chat' | 'profile';

export default function App() {
  // session lives in an HttpOnly cookie - the backend is the only source of truth
  const { state, login, logout } = useAuth();

  // track which screen is currently visible
  const [activeView, setActiveView] = useState<View>(() =>
    localStorage.getItem('chatActiveView') === 'profile' ? 'profile' : 'chat'
  );

  // get theme from storage to pass to profile screen
  const currentTheme = localStorage.getItem('chat-theme') || 'jasny';

  // save active view to memory every time it changes
  useEffect(() => {
    localStorage.setItem('chatActiveView', activeView);
  }, [activeView]);

  const handleLogout = () => {
    setActiveView('chat');
    void logout();
  };

  // checking the session with the backend
  if (state.status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" aria-label="Loading" />
      </div>
    );
  }

  // no session - only KSI login is possible
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
        selectedTheme={currentTheme}
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
