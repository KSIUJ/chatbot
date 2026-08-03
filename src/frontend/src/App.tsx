import { useState } from 'react';
import ChatScreen from './ChatScreen';
import LoginScreen from './LoginScreen'; // adjust name if your login file is named differently

export default function App() {
  
  // check local storage first to remember login state after refresh
  const [isLoggedIn, setIsLoggedIn] = useState(() => {
    return localStorage.getItem('isLoggedIn') === 'true';
  });

  // fired when user logs in successfully
  const handleLogin = () => {
    setIsLoggedIn(true);
    localStorage.setItem('isLoggedIn', 'true'); // save to memory
  };

  // handle logout - commented out for now since we don't have a logout button yet
  /*
  const handleLogout = () => {
    setIsLoggedIn(false);
    localStorage.removeItem('isLoggedIn'); 
  };
  */

  // show login screen if not logged in
  if (!isLoggedIn) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  // show main chat view
  return <ChatScreen />;
}