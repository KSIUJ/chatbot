import { useState } from 'react';
import LoginScreen from './LoginScreen';
import ChatScreen from './ChatScreen';

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const handleLogin = () => {
    setIsLoggedIn(true);
  };

  return (
    <div>
      {/* Jeśli isLoggedIn to true, pokaż ChatScreen. Jeśli false - pokaż LoginScreen */}
      {isLoggedIn ? (
        <ChatScreen />
      ) : (
        <LoginScreen onLogin={handleLogin} />
      )}
    </div>
  );
}