import type { AttachmentType, IncidentSource, LimitMode, ReviewStatus } from '../admin/adminApi';
import type { AdminTab } from '../admin/tabs';
import type { LoginError } from '../auth/redirect';
import type { ReportReason } from '../chat/feedback';
import type { SourceKind } from '../chat/sources';
import type { ThemePreference } from './themes';
import { de } from './translations/de';
import { en } from './translations/en';
import { es } from './translations/es';
import { fr } from './translations/fr';
import { it } from './translations/it';
import { pl } from './translations/pl';
import { uk } from './translations/uk';

// Interface language code - the same languages as the KSI Keycloak. Also the
// value of <html lang>, the answer language sent to the API and ui_locales
// passed to the KSI login page.
export type HtmlLang = 'pl' | 'en' | 'de' | 'es' | 'fr' | 'it' | 'uk';

// Strings of the admin panel (only shown to the admin group).
export interface AdminTranslation {
  title: string;
  backToChat: string;
  sections: string;
  tabs: Record<AdminTab, string>;
  loadError: string;
  saveError: string;
  saved: string;
  save: string;
  refresh: string;
  previousPage: string;
  nextPage: string;
  pageInfo: (from: number, to: number, total: number) => string;
  unknown: string;
  // limits
  globalLimits: string;
  dailyQuestionLimit: string;
  attachments: string;
  attachmentsNote: string;
  maxFileMb: string;
  maxFilesPerMessage: string;
  maxAttachmentsPerDay: string;
  allowedTypes: string;
  typeNames: Record<AttachmentType, string>;
  defaultValue: (value: string) => string;
  users: string;
  searchUsers: string;
  search: string;
  noUsers: string;
  usedToday: string;
  lastLogin: string;
  limitModes: Record<LimitMode, string>;
  customLimit: string;
  blockedHint: string;
  note: string;
  editLimit: string;
  // reports and incidents
  status: string;
  allStatuses: string;
  statuses: Record<ReviewStatus, string>;
  exportCsv: string;
  noReports: string;
  noIncidents: string;
  question: string;
  answer: string;
  noQuestion: string;
  answerGone: string;
  comment: string;
  reason: string;
  answerLanguage: string;
  reportedAt: string;
  reviewedAt: string;
  adminNote: string;
  resolve: string;
  dismiss: string;
  reopen: string;
  showDetails: string;
  hideDetails: string;
  person: string;
  deletedAccount: string;
  rules: string;
  detectedBy: string;
  incidentSources: Record<IncidentSource, string>;
  // diagnostics
  model: string;
  provider: string;
  modelName: string;
  uptime: string;
  calls: string;
  errors: string;
  avgLatency: string;
  p95Latency: string;
  lastError: string;
  recentWindow: (count: number) => string;
  usage: string;
  questionsToday: string;
  questions7d: string;
  activeToday: string;
  active7d: string;
  data: string;
  usersCount: string;
  conversations: string;
  messages: string;
  openReports: string;
  openIncidents: string;
  ragIndex: string;
  vectorCount: string;
  lexicalCount: string;
  lexicalSize: string;
  lastIngest: string;
  storage: string;
  databaseSize: string;
  diskFree: string;
  unavailable: string;
  generatedAt: (time: string) => string;
}

export interface Translation {
  // value of <html lang>
  htmlLang: HtmlLang;
  // name of the language in itself, for the settings menu
  languageName: string;
  // the "follow the browser" option in the language menu
  systemLanguage: string;
  appTitle: string;
  loading: string;
  ksiWebsite: string;
  // login screen
  logIn: string;
  tryAgain: string;
  // second action after a refused login: Keycloak form despite the SSO session
  logInAnotherAccount: string;
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
  openMenu: string;
  closeMenu: string;
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
  sources: (count: number) => string;
  sourceKinds: Record<SourceKind, string>;
  // rating and reporting an answer
  answerActions: string;
  rateUp: string;
  rateDown: string;
  feedbackError: string;
  report: string;
  reported: string;
  reportTitle: string;
  reportReasonLabel: string;
  reportReasons: Record<ReportReason, string>;
  reportComment: string;
  reportSubmit: string;
  reportError: string;
  cancel: string;
  // daily question limit
  rateLimited: (limit: number, time: string) => string;
  usageToday: (used: number, limit: number) => string;
  admin: AdminTranslation;
}

export const translations: Record<HtmlLang, Translation> = { pl, en, de, es, fr, it, uk };

// Order of the KSI Keycloak language menu (alphabetical by code).
export const LANGUAGES: readonly HtmlLang[] = ['de', 'en', 'es', 'fr', 'it', 'pl', 'uk'];

// "system" follows the browser language, like the "systemowy" theme.
export type LanguagePreference = 'system' | HtmlLang;

// Options of the settings menu: "system" first, then the languages.
export const LANGUAGE_PREFERENCES: readonly LanguagePreference[] = ['system', ...LANGUAGES];

// Used when "system" finds none of the supported languages in the browser.
export const FALLBACK_LANGUAGE: HtmlLang = 'en';

export const LANGUAGE_STORAGE_KEY = 'chatLanguage';

// Values stored by versions that had only Polish, English and French.
// (a Map, so stored junk like "constructor" never hits Object.prototype)
const LEGACY_PREFERENCES: ReadonlyMap<string, HtmlLang> = new Map([
  ['polski', 'pl'],
  ['angielski', 'en'],
  ['francuski', 'fr'],
]);

function asLanguage(value: string): HtmlLang | null {
  return LANGUAGES.find((key) => key === value) ?? null;
}

export function parseLanguagePreference(value: string | null): LanguagePreference {
  if (value === null || value === 'system') return 'system';
  return asLanguage(value) ?? LEGACY_PREFERENCES.get(value) ?? 'system';
}

// Language to render: the chosen one, or for "system" the first browser
// language we support (matched by its primary tag, e.g. "pl-PL" -> "pl").
export function resolveLanguage(preference: LanguagePreference, browserLanguages: readonly string[]): HtmlLang {
  if (preference !== 'system') return preference;
  for (const tag of browserLanguages) {
    const language = asLanguage(tag.toLowerCase().split('-')[0]);
    if (language !== null) return language;
  }
  return FALLBACK_LANGUAGE;
}
