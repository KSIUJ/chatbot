import { useState } from 'react';
import ChatScreen from './features/Chat/ChatScreen';
import LoginScreen from './features/Auth/LoginScreen'; 
import ProfileScreen from './features/Profile/ProfileScreen'; 

export default function App() {
  // get email from local storage to remember login state after refresh
  const [userEmail, setUserEmail] = useState<string | null>(() => {
    return localStorage.getItem('userEmail');
  });

  // track which screen is currently visible
  const [activeView, setActiveView] = useState<'chat' | 'profile'>('chat');

  // get theme from storage to pass to profile screen (defaults to jasny)
  const currentTheme = localStorage.getItem('chat-theme') || 'jasny';

  // fired when user logs in successfully (receives email from login screen)
  const handleLogin = (email: string) => {
    setUserEmail(email);
    localStorage.setItem('userEmail', email); // save to memory
  };

  // handle logout - clears session and resets view
  const handleLogout = () => {
    setUserEmail(null);
    setActiveView('chat');
    localStorage.removeItem('userEmail'); 
  };

  // show login screen if not logged in (no email in state)
  if (!userEmail) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  // show profile screen if selected
  if (activeView === 'profile') {
    return (
      <ProfileScreen 
        email={userEmail}
        onClose={() => setActiveView('chat')}
        onLogout={handleLogout}
        selectedTheme={currentTheme}
      />
    );
  }

  // show main chat view
  return (
    <ChatScreen 
      onOpenProfile={() => setActiveView('profile')}
      onLogout={handleLogout} 
    />
  );
}