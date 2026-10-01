import type { LoginError } from '../auth/redirect';
import type { ThemePreference } from './themes';

export interface Translation {
  // value of <html lang>
  htmlLang: string;
  // name of the language in itself, for the settings menu
  languageName: string;
  appTitle: string;
  loading: string;
  ksiWebsite: string;
  // login screen
  authorization: string;
  logIn: string;
  tryAgain: string;
  redirecting: string;
  loginErrors: Record<LoginError, string>;
  // sidebar
  newChat: string;
  recent: string;
  noChats: string;
  untitled: string;
  deleteChat: string;
  deleteConfirm: string;
  historyNote: (max: number, days: number) => string;
  historyError: string;
  language: string;
  theme: string;
  themeNames: Record<ThemePreference, string>;
  settings: string;
  back: string;
  logout: string;
  // conversation
  greeting: string;
  inputPlaceholder: string;
  waitingPlaceholder: string;
  send: string;
  stop: string;
  disclaimer: string;
  copy: string;
  copied: string;
  retry: string;
  stopped: string;
  error: string;
  loadError: string;
}

const APP_TITLE = 'Chatbot WMiI UJ';

const polski: Translation = {
  htmlLang: 'pl',
  languageName: 'Polski',
  appTitle: APP_TITLE,
  loading: 'Ładowanie...',
  ksiWebsite: 'Strona KSI',
  authorization: 'Autoryzacja',
  logIn: 'Zaloguj się przez KSI',
  tryAgain: 'Spróbuj ponownie',
  redirecting: 'Przekierowywanie...',
  loginErrors: {
    login_incomplete:
      'Logowanie nie zostało dokończone. Upewnij się, że ta strona może zapisywać ciasteczka, i spróbuj ponownie.',
    not_authenticated: 'Zaloguj się kontem KSI.',
    session_expired: 'Sesja wygasła. Zaloguj się ponownie.',
    not_member: 'Chatbot jest dostępny tylko dla członków KSI (grupa Członek).',
    provider_unavailable: 'Serwer logowania KSI jest niedostępny. Spróbuj ponownie za chwilę.',
    access_denied: 'Logowanie zostało anulowane.',
    invalid_state: 'Logowanie trwało zbyt długo lub zostało rozpoczęte w innej karcie. Spróbuj ponownie.',
    login_failed: 'Logowanie nie powiodło się. Spróbuj ponownie.',
    forbidden_origin: 'Żądanie zostało odrzucone. Odśwież stronę.',
  },
  newChat: 'Nowy czat',
  recent: 'Ostatnie',
  noChats: 'Brak rozmów',
  untitled: 'Rozmowa',
  deleteChat: 'Usuń rozmowę',
  deleteConfirm: 'Usunąć tę rozmowę?',
  historyNote: (max, days) => `Przechowujemy ${max} ostatnich rozmów. Nieużywane usuwamy po ${days} dniach.`,
  historyError: 'Nie udało się wczytać historii.',
  language: 'Język',
  theme: 'Motyw',
  themeNames: {
    systemowy: 'systemowy',
    jasny: 'jasny',
    ciemny: 'ciemny',
  },
  settings: 'Ustawienia',
  back: 'Wstecz',
  logout: 'Wyloguj się',
  greeting: 'Cześć! Jestem wirtualnym asystentem Wydziału Matematyki i Informatyki. W czym mogę Ci dzisiaj pomóc?',
  inputPlaceholder: 'Zapytaj Chatbota',
  waitingPlaceholder: 'Odpowiada...',
  send: 'Wyślij',
  stop: 'Zatrzymaj',
  disclaimer: 'Chatbot to AI i może popełniać błędy. Zweryfikuj ważne informacje na stronie wydziału.',
  copy: 'Kopiuj',
  copied: 'Skopiowano',
  retry: 'Ponów',
  stopped: 'Przerwano.',
  error: 'Nie udało się uzyskać odpowiedzi. Spróbuj ponownie.',
  loadError: 'Nie udało się wczytać rozmowy.',
};

const angielski: Translation = {
  htmlLang: 'en',
  languageName: 'English',
  appTitle: APP_TITLE,
  loading: 'Loading...',
  ksiWebsite: 'KSI website',
  authorization: 'Authorization',
  logIn: 'Log in with KSI',
  tryAgain: 'Try again',
  redirecting: 'Redirecting...',
  loginErrors: {
    login_incomplete: 'Login did not complete. Make sure cookies are enabled for this site and try again.',
    not_authenticated: 'Please log in with your KSI account.',
    session_expired: 'Your session has expired. Please log in again.',
    not_member: 'The chatbot is available to KSI members only (group Członek).',
    provider_unavailable: 'The KSI login server is unavailable. Please try again in a moment.',
    access_denied: 'Login was cancelled.',
    invalid_state: 'Login took too long or was started in another tab. Please try again.',
    login_failed: 'Login failed. Please try again.',
    forbidden_origin: 'Request was rejected. Please reload the page.',
  },
  newChat: 'New chat',
  recent: 'Recent',
  noChats: 'No conversations',
  untitled: 'Conversation',
  deleteChat: 'Delete conversation',
  deleteConfirm: 'Delete this conversation?',
  historyNote: (max, days) => `We keep your ${max} most recent chats. Unused ones are deleted after ${days} days.`,
  historyError: 'Could not load history.',
  language: 'Language',
  theme: 'Theme',
  themeNames: {
    systemowy: 'system',
    jasny: 'light',
    ciemny: 'dark',
  },
  settings: 'Settings',
  back: 'Back',
  logout: 'Log out',
  greeting: "Hi! I'm the virtual assistant of the Faculty of Mathematics and Computer Science. How can I help you today?",
  inputPlaceholder: 'Ask the Chatbot',
  waitingPlaceholder: 'Answering...',
  send: 'Send',
  stop: 'Stop',
  disclaimer: 'Chatbot is an AI and may make mistakes. Verify important information on the faculty website.',
  copy: 'Copy',
  copied: 'Copied',
  retry: 'Retry',
  stopped: 'Stopped.',
  error: 'Could not get an answer. Please try again.',
  loadError: 'Could not load this conversation.',
};

const francuski: Translation = {
  htmlLang: 'fr',
  languageName: 'Français',
  appTitle: APP_TITLE,
  loading: 'Chargement...',
  ksiWebsite: 'Site du KSI',
  authorization: 'Autorisation',
  logIn: 'Se connecter avec KSI',
  tryAgain: 'Réessayer',
  redirecting: 'Redirection...',
  loginErrors: {
    login_incomplete:
      "La connexion n'a pas abouti. Vérifiez que ce site peut enregistrer des cookies, puis réessayez.",
    not_authenticated: 'Connectez-vous avec votre compte KSI.',
    session_expired: 'Votre session a expiré. Reconnectez-vous.',
    not_member: 'Le chatbot est réservé aux membres du KSI (groupe Członek).',
    provider_unavailable: 'Le serveur de connexion KSI est indisponible. Réessayez dans un instant.',
    access_denied: 'La connexion a été annulée.',
    invalid_state: 'La connexion a pris trop de temps ou a été lancée dans un autre onglet. Réessayez.',
    login_failed: 'La connexion a échoué. Réessayez.',
    forbidden_origin: 'La requête a été refusée. Rechargez la page.',
  },
  newChat: 'Nouvelle discussion',
  recent: 'Récentes',
  noChats: 'Aucune conversation',
  untitled: 'Conversation',
  deleteChat: 'Supprimer la conversation',
  deleteConfirm: 'Supprimer cette conversation ?',
  historyNote: (max, days) =>
    `Nous conservons vos ${max} dernières conversations. Celles inutilisées sont supprimées après ${days} jours.`,
  historyError: "Impossible de charger l'historique.",
  language: 'Langue',
  theme: 'Thème',
  themeNames: {
    systemowy: 'système',
    jasny: 'clair',
    ciemny: 'sombre',
  },
  settings: 'Paramètres',
  back: 'Retour',
  logout: 'Se déconnecter',
  greeting:
    "Bonjour ! Je suis l'assistant virtuel de la Faculté de mathématiques et d'informatique. Comment puis-je vous aider aujourd'hui ?",
  inputPlaceholder: 'Posez une question au Chatbot',
  waitingPlaceholder: 'Réponse en cours...',
  send: 'Envoyer',
  stop: 'Arrêter',
  disclaimer:
    "Le chatbot est une IA et peut se tromper. Vérifiez les informations importantes sur le site de la faculté.",
  copy: 'Copier',
  copied: 'Copié',
  retry: 'Réessayer',
  stopped: 'Interrompu.',
  error: "Impossible d'obtenir une réponse. Réessayez.",
  loadError: 'Impossible de charger cette conversation.',
};

// Keys are the values stored in localStorage - keep them unchanged.
export const translations = { polski, angielski, francuski } as const;

export type LangKey = keyof typeof translations;

// Order shown in the settings menu.
export const LANGUAGES: readonly LangKey[] = ['polski', 'angielski', 'francuski'];

export const LANGUAGE_STORAGE_KEY = 'chatLanguage';

export function parseLanguage(value: string | null): LangKey {
  return LANGUAGES.find((key) => key === value) ?? 'polski';
}
