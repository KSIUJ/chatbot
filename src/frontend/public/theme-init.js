// Puts the theme class on <html> before the first paint, so a dark-mode user
// never sees a light flash while the app bundle loads. A plain file (not an
// inline script) to stay within the CSP's script-src 'self'.
// Mirrors THEME_STORAGE_KEY and resolveTheme() in
// src/features/preferences/themes.ts, and the occasion cache of
// src/features/occasion/occasion.ts (OCCASION_CACHE_KEY, OCCASION_TOGGLE_KEY,
// CACHE_MAX_AGE_MS, cacheOccasion); React keeps all of it in sync afterwards.
(function () {
  var MAX_AGE_MS = 12 * 60 * 60 * 1000;
  var TOKEN_NAME = /^--ksi-[a-z0-9-]+$/;
  // exactly what occasionVars() produces: #rrggbb or color-mix() of two of them
  var TOKEN_VALUE = /^(#[0-9a-f]{6}|color-mix\(in srgb, #[0-9a-f]{6} \d{1,3}%, #[0-9a-f]{6}\))$/i;
  var HEX_COLOR = /^#[0-9a-f]{6}$/i;
  var root = document.documentElement;
  var stored = null;
  var occasion = null;
  try {
    stored = window.localStorage.getItem('chatTheme');
    if (window.localStorage.getItem('chatOccasionThemes') !== 'off') {
      var entry = JSON.parse(window.localStorage.getItem('chatOccasion') || 'null');
      var age = entry && typeof entry.savedAt === 'number' ? Date.now() - entry.savedAt : -1;
      if (entry && entry.v === 1 && age >= 0 && age <= MAX_AGE_MS && entry.occasion) occasion = entry;
    }
  } catch {
    // storage blocked (privacy mode) or a broken entry: follow the device below
  }
  var dark =
    stored === 'ciemny' ||
    (stored !== 'jasny' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  // a ksi.sh occasion with its own dark look overrides the user's choice
  if (occasion && occasion.occasion.dark === true) dark = true;
  root.classList.toggle('dark', dark);
  if (!dark || !occasion || typeof occasion.vars !== 'object' || occasion.vars === null) return;
  for (var name in occasion.vars) {
    var value = occasion.vars[name];
    if (TOKEN_NAME.test(name) && typeof value === 'string' && TOKEN_VALUE.test(value)) {
      root.style.setProperty(name, value);
    }
  }
  // like themeColorFor(): the occasion's own colour, else its background
  var palette = occasion.occasion.palette;
  var color = occasion.occasion.themeColor || (palette && palette['night-950']);
  if (typeof color === 'string' && HEX_COLOR.test(color)) {
    document.querySelectorAll('meta[name="theme-color"]').forEach(function (meta) {
      meta.content = color;
    });
  }
})();
