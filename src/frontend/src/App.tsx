import { useState } from 'react';
import LoginScreen from './LoginScreen';
import ChatScreen from './ChatScreen'; // Importujemy nowy ekran czatu

function App() {
  // Zmienna isLoggedIn przechowuje informację, czy użytkownik jest zalogowany
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  // Funkcja, która uruchomi się po kliknięciu "Zaloguj się"
  const handleLogin = () => {
    setIsLoggedIn(true);
  };

  return (
    <>
      {/* Jeśli jest zalogowany (isLoggedIn === true), pokaż ChatScreen. 
          W przeciwnym razie pokaż LoginScreen */}
      {isLoggedIn ? (
        <ChatScreen />
      ) : (
        <LoginScreen onLogin={handleLogin} />
      )}
    </>
  );
}

export default App;