export const translations = {
  polski: {
    appTitle: "Chatbot WMiI",
    newChat: "Nowy czat",
    recent: "Ostatnie",
    noChats: "Brak rozmów",
    untitled: "Rozmowa",
    deleteChat: "Usuń rozmowę",
    deleteConfirm: "Usunąć tę rozmowę?",
    historyNote: (max: number, days: number) =>
      `Przechowujemy ${max} ostatnich rozmów. Nieużywane usuwamy po ${days} dniach.`,
    historyError: "Nie udało się wczytać historii.",
    language: "Język",
    theme: "Motyw",
    settings: "Ustawienia",
    logout: "Wyloguj się",
    greeting: "Cześć! Jestem wirtualnym asystentem Wydziału Matematyki i Informatyki. W czym mogę Ci dzisiaj pomóc?",
    inputPlaceholder: "Zapytaj Chatbota",
    waitingPlaceholder: "Odpowiada...",
    send: "Wyślij",
    stop: "Zatrzymaj",
    disclaimer: "Chatbot to AI i może popełniać błędy. Zweryfikuj ważne informacje na stronie wydziału.",
    copy: "Kopiuj",
    copied: "Skopiowano",
    retry: "Ponów",
    stopped: "Przerwano.",
    error: "Nie udało się uzyskać odpowiedzi. Spróbuj ponownie.",
    loadError: "Nie udało się wczytać rozmowy.",
    themeNames: {
      systemowy: "systemowy",
      jasny: "jasny",
      ciemny: "ciemny",
    },
  },
  angielski: {
    appTitle: "WMiI Chatbot",
    newChat: "New chat",
    recent: "Recent",
    noChats: "No conversations",
    untitled: "Conversation",
    deleteChat: "Delete conversation",
    deleteConfirm: "Delete this conversation?",
    historyNote: (max: number, days: number) =>
      `We keep your ${max} most recent chats. Unused ones are deleted after ${days} days.`,
    historyError: "Could not load history.",
    language: "Language",
    theme: "Theme",
    settings: "Settings",
    logout: "Log out",
    greeting: "Hi! I'm the virtual assistant of the Faculty of Mathematics and Computer Science. How can I help you today?",
    inputPlaceholder: "Ask the Chatbot",
    waitingPlaceholder: "Answering...",
    send: "Send",
    stop: "Stop",
    disclaimer: "Chatbot is an AI and may make mistakes. Verify important information on the faculty website.",
    copy: "Copy",
    copied: "Copied",
    retry: "Retry",
    stopped: "Stopped.",
    error: "Could not get an answer. Please try again.",
    loadError: "Could not load this conversation.",
    themeNames: {
      systemowy: "system",
      jasny: "light",
      ciemny: "dark",
    },
  },
};

export type LangKey = keyof typeof translations;
export type Translation = (typeof translations)[LangKey];

export const LANGUAGE_STORAGE_KEY = 'chatLanguage';

export function parseLanguage(value: string | null): LangKey {
  return value === 'angielski' ? 'angielski' : 'polski';
}
