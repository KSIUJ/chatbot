import { useState, useEffect } from 'react';
import ChatScreen from './features/Chat/ChatScreen';
import LoginScreen from './features/Auth/LoginScreen'; 
import ProfileScreen from './features/Profile/ProfileScreen'; 
import RegisterScreen from './features/Auth/RegisterScreen';

export default function App() {
  // get email from local storage to remember login state
  const [userEmail, setUserEmail] = useState<string | null>(() => {
    return localStorage.getItem('userEmail');
  });

  // track if user chose to continue without logging in
  const [isGuest, setIsGuest] = useState<boolean>(() => {
    return localStorage.getItem('isGuest') === 'true';
  });

  // track which screen is currently visible
  const [activeView, setActiveView] = useState<'chat' | 'profile' | 'login' | 'register'>(() => {
    const savedView = localStorage.getItem('activeView');
    if (savedView === 'profile' || savedView === 'login' || savedView === 'register') {
      return savedView;
    }
    return 'chat';
  });

  // get theme from storage to pass to profile screen
  const currentTheme = localStorage.getItem('chat-theme') || 'jasny';

  // save active view to memory every time it changes
  useEffect(() => {
    localStorage.setItem('activeView', activeView);
  }, [activeView]);

  // fired when user logs in successfully
  const handleLogin = (email: string) => {
    setUserEmail(email);
    setIsGuest(false);
    localStorage.setItem('userEmail', email); 
    localStorage.removeItem('isGuest'); 
    setActiveView('chat');
  };

  // fired when user clicks continue without logging in
  const handleContinueAsGuest = () => {
    setIsGuest(true);
    localStorage.setItem('isGuest', 'true');
    setActiveView('chat');
  };

  // handle logout - clears session, guest status and resets view
  const handleLogout = () => {
    setUserEmail(null);
    setIsGuest(false);
    setActiveView('chat');
    localStorage.removeItem('userEmail'); 
    localStorage.removeItem('isGuest'); 
    localStorage.removeItem('activeView'); 
  };

  // if no user email and not a guest, show login or register screen
  if (!userEmail && !isGuest && activeView !== 'register') {
    return (
      <LoginScreen 
        onLogin={handleLogin} 
        onContinueAsGuest={handleContinueAsGuest} 
        onGoToRegister={() => setActiveView('register')}
      />
    );
  }

  // show register screen
  if (activeView === 'register') {
    return (
      <RegisterScreen 
        onGoBackToLogin={() => setActiveView('login')} 
      />
    );
  }

  // show profile screen if selected
  if (activeView === 'profile') {
    return (
      <ProfileScreen 
        email={userEmail || 'Guest'}
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