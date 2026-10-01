// Conversations live on the server; the browser only remembers which one is
// open. Cleared on logout and on account change, so on a shared computer the
// next person does not land in someone else's conversation.
export const ACTIVE_CONVERSATION_KEY = 'chatConversationId';

// Who the remembered conversation belongs to.
const CHAT_OWNER_KEY = 'chatOwner';

// Leftovers of earlier versions: password login, guest mode, chat kept in
// localStorage, RAG slider, profile view, duplicate theme key.
const LEGACY_KEYS = [
  'userEmail',
  'isGuest',
  'isLoggedIn',
  'activeView',
  'chatActiveView',
  'chat-theme',
  'chatMessages',
  'chatRagCount',
] as const;

// Remembers the open conversation. Without one, the old id is forgotten only
// when `canForget` - i.e. once it is known that nothing is open on purpose.
export function rememberActiveConversation(
  activeId: string | null,
  canForget: boolean,
  storage: Pick<Storage, 'setItem' | 'removeItem'> = localStorage,
): void {
  if (activeId !== null) storage.setItem(ACTIVE_CONVERSATION_KEY, activeId);
  else if (canForget) storage.removeItem(ACTIVE_CONVERSATION_KEY);
}

export function clearChatStorage(): void {
  localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
  localStorage.removeItem(CHAT_OWNER_KEY);
}

// Called once the session is confirmed: drop state that belongs to another account.
export function claimChatStorage(userId: string): void {
  for (const key of LEGACY_KEYS) localStorage.removeItem(key);
  if (localStorage.getItem(CHAT_OWNER_KEY) !== userId) {
    clearChatStorage();
    localStorage.setItem(CHAT_OWNER_KEY, userId);
  }
}
