import { useSyncExternalStore } from 'react';
import { resolveTheme, type ThemeKey, type ThemePreference } from './themes';

const DARK_QUERY = '(prefers-color-scheme: dark)';

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(DARK_QUERY);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}

function systemPrefersDark(): boolean {
  return window.matchMedia(DARK_QUERY).matches;
}

// Theme to render for a preference; "systemowy" follows the device live
// (switching the OS to dark mode re-renders without a reload).
export function useResolvedTheme(preference: ThemePreference): ThemeKey {
  const prefersDark = useSyncExternalStore(subscribe, systemPrefersDark, () => false);
  return resolveTheme(preference, prefersDark);
}
