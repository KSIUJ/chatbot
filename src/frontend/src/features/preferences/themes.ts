// Concrete themes. The colours live in src/index.css (KSI Keycloak tokens);
// "ciemny" switches them through the .dark class on <html>.
export const THEME_KEYS = ['jasny', 'ciemny'] as const;

export type ThemeKey = (typeof THEME_KEYS)[number];

// What the user picked in settings: a concrete theme or "follow the device".
export type ThemePreference = ThemeKey | 'systemowy';

export const DEFAULT_THEME_PREFERENCE: ThemePreference = 'systemowy';

// Order shown in the settings menu.
export const THEME_PREFERENCES: readonly ThemePreference[] = ['systemowy', 'jasny', 'ciemny'];

// Also read by public/theme-init.js (before the first paint) - keep in sync.
export const THEME_STORAGE_KEY = 'chatTheme';

// Class on <html> that turns on the dark tokens and Tailwind's `dark:` variant.
export const DARK_CLASS = 'dark';

// Unknown or removed themes fall back to the default.
export function parseThemePreference(value: string | null): ThemePreference {
  return THEME_PREFERENCES.find((option) => option === value) ?? DEFAULT_THEME_PREFERENCE;
}

// Theme actually rendered: "systemowy" maps to light/dark by the device setting.
export function resolveTheme(preference: ThemePreference, systemPrefersDark: boolean): ThemeKey {
  if (preference !== 'systemowy') return preference;
  return systemPrefersDark ? 'ciemny' : 'jasny';
}

export function isDarkTheme(theme: ThemeKey): boolean {
  return theme === 'ciemny';
}

// Puts the resolved theme on <html>, so the CSS tokens follow it.
export function applyTheme(root: { classList: Pick<DOMTokenList, 'toggle'> }, theme: ThemeKey): void {
  root.classList.toggle(DARK_CLASS, isDarkTheme(theme));
}
