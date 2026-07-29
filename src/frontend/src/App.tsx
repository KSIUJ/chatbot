import { useState } from 'react';
import LoginScreen from './LoginScreen';
import ChatScreen from './ChatScreen';

export default function App() {
  // Zmienna stanu, która pamięta, czy użytkownik jest zalogowany
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  // Funkcja, która zmienia stan na "zalogowany"
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