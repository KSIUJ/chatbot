// Conversations live on the server; the page always opens on a new chat, so
// the browser keeps no conversation of its own - only who used it last, to
// clean up after an account change on a shared computer.

// Who used the chat in this browser last.
const CHAT_OWNER_KEY = 'chatOwner';

// Leftovers of earlier versions: password login, guest mode, chat kept in
// localStorage, RAG slider, profile view, duplicate theme key, and the id of
// the conversation reopened after a reload (no longer reopened).
const LEGACY_KEYS = [
  'userEmail',
  'isGuest',
  'isLoggedIn',
  'activeView',
  'chatActiveView',
  'chat-theme',
  'chatMessages',
  'chatRagCount',
  'chatConversationId',
] as const;

export function clearChatStorage(storage: Pick<Storage, 'removeItem'> = localStorage): void {
  storage.removeItem(CHAT_OWNER_KEY);
  storage.removeItem('chatConversationId');
}

// Called once the session is confirmed: drop leftovers and state of another account.
export function claimChatStorage(
  userId: string,
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> = localStorage,
): void {
  for (const key of LEGACY_KEYS) storage.removeItem(key);
  if (storage.getItem(CHAT_OWNER_KEY) !== userId) {
    clearChatStorage(storage);
    storage.setItem(CHAT_OWNER_KEY, userId);
  }
}
