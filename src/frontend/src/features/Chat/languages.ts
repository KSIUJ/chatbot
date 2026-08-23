export const translations = {
  polski: {
    appTitle: "Chatbot WMiI",
    newChat: "Nowy czat",
    recent: "Ostatnie",
    chat1: "Zasady przyznawania stypendiów...",
    chat2: "Regulamin studiów WMiI",
    chat3: "Kontakt do dziekanatu",
    language: "Język",
    theme: "Motyw",
    ragContexts: "Konteksty RAG",
    settings: "Ustawienia",
    account: "Konto",
    logout: "Wyloguj się",
    botGreeting: "Cześć! Jestem wirtualnym asystentem Wydziału Matematyki i Informatyki. W czym mogę Ci dzisiaj pomóc?",
    botReply: "testowa odp",
    inputPlaceholder: "Zapytaj Chatbota",
    disclaimer: "Chatbot to AI i może popełniać błędy. Zweryfikuj ważne informacje na stronie wydziału.",
    copy: "Kopiuj",
    copied: "Skopiowano",
    themeNames: {
      jasny: "jasny",
      ciemny: "ciemny",
      granatowy: "granatowy",
      różowy: "różowy"
    }
  },
  angielski: {
    appTitle: "WMiI Chatbot",
    newChat: "New chat",
    recent: "Recent",
    chat1: "Scholarship rules...",
    chat2: "WMiI study regulations",
    chat3: "Dean's office contact",
    language: "Language",
    theme: "Theme",
    ragContexts: "RAG Contexts",
    settings: "Settings",
    account: "Account",
    logout: "Log out",
    botGreeting: "Hello! I am the virtual assistant of the Faculty of Mathematics and Computer Science. How can I help you today?",
    botReply: "test reply",
    inputPlaceholder: "Ask Chatbot",
    disclaimer: "Chatbot is an AI and may make mistakes. Verify important information on the faculty website.",
    copy: "Copy",
    copied: "Copied",
    themeNames: {
      jasny: "light",
      ciemny: "dark",
      granatowy: "navy",
      różowy: "pink"
    }
  }
};

export type LangKey = keyof typeof translations;