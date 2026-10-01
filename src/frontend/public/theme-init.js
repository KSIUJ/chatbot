// Puts the theme class on <html> before the first paint, so a dark-mode user
// never sees a light flash while the app bundle loads. A plain file (not an
// inline script) to stay within the CSP's script-src 'self'.
// Mirrors THEME_STORAGE_KEY and resolveTheme() in
// src/features/preferences/themes.ts; React keeps the class in sync afterwards.
(function () {
  var stored = null;
  try {
    stored = window.localStorage.getItem('chatTheme');
  } catch {
    // storage blocked (privacy mode): follow the device below
  }
  var dark =
    stored === 'ciemny' ||
    (stored !== 'jasny' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', dark);
})();
