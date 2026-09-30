// Klucze localStorage z trescia rozmowy (useChat). Czyszczone przy
// wylogowaniu i przy zmianie konta, zeby na wspolnym komputerze nikt nie
// zobaczyl cudzej rozmowy.
const CHAT_CONTENT_KEYS = ['chatMessages', 'chatConversationId'] as const;

// Kto jest wlascicielem rozmowy zapisanej w localStorage.
const CHAT_OWNER_KEY = 'chatOwner';

// Pozostalosci po starym logowaniu haslem i trybie goscia.
const LEGACY_KEYS = ['userEmail', 'isGuest', 'isLoggedIn', 'activeView'] as const;

export function clearChatStorage(): void {
  for (const key of CHAT_CONTENT_KEYS) localStorage.removeItem(key);
  localStorage.removeItem(CHAT_OWNER_KEY);
}

// Wywolywane po potwierdzeniu zalogowania: jesli zapisana rozmowa nalezy
// do kogos innego, zostaje usunieta.
export function claimChatStorage(userId: string): void {
  for (const key of LEGACY_KEYS) localStorage.removeItem(key);
  if (localStorage.getItem(CHAT_OWNER_KEY) !== userId) {
    clearChatStorage();
    localStorage.setItem(CHAT_OWNER_KEY, userId);
  }
}
