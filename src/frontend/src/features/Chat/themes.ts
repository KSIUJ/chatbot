export const themeStyles = {
  jasny: {
    app: "bg-neutral-50",
    sidebar: "bg-white border-neutral-200",
    border: "border-neutral-200",
    text: "text-neutral-900",
    textMuted: "text-neutral-500",
    hover: "hover:bg-neutral-100",
    active: "bg-neutral-200",
    botIcon: "bg-neutral-600",
    msgBox: "bg-white border border-neutral-200 text-neutral-800 shadow-sm",
    userMsgBox: "bg-neutral-800 border-0 text-white shadow-sm",
    inputBox: "bg-white border-neutral-200 text-neutral-900 focus:ring-neutral-500/50",
    sendBtn: "bg-neutral-800 hover:bg-neutral-900 text-white",
    popover: "bg-white border-neutral-200 shadow-xl",
    copiedIcon: "text-neutral-800",
  },
  ciemny: {
    app: "bg-[#121212]",
    sidebar: "bg-[#1a1a1a] border-neutral-800",
    border: "border-neutral-800",
    text: "text-neutral-200",
    textMuted: "text-neutral-400",
    hover: "hover:bg-neutral-800",
    active: "bg-neutral-700",
    botIcon: "bg-neutral-500",
    msgBox: "bg-[#252525] border-0 text-neutral-100 shadow-md",
    userMsgBox: "bg-[#333333] border-0 text-neutral-100 shadow-md",
    inputBox: "bg-[#1e1e1e] border-neutral-800 text-neutral-200 focus:ring-neutral-600/50",
    sendBtn: "bg-neutral-700 hover:bg-neutral-600 text-white",
    popover: "bg-[#2c2c2c] border-neutral-800 shadow-xl",
    copiedIcon: "text-neutral-200",
  },
};

export type ThemeKey = keyof typeof themeStyles;
export type ThemeStyle = (typeof themeStyles)[ThemeKey];

// What the user picked in settings: a concrete theme or "follow the device".
export type ThemePreference = ThemeKey | 'systemowy';

export const DEFAULT_THEME_PREFERENCE: ThemePreference = 'systemowy';

// Order shown in the settings menu.
export const THEME_PREFERENCES: readonly ThemePreference[] = ['systemowy', 'jasny', 'ciemny'];

export const THEME_STORAGE_KEY = 'chatTheme';

// Unknown or removed themes (e.g. the old "granatowy") fall back to the default.
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
