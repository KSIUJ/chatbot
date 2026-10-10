import { useEffect, useState } from 'react';
import { apiJson } from '../../lib/api';
import {
  OCCASION_CACHE_KEY,
  cacheOccasion,
  parseOccasion,
  readCachedOccasion,
  sameOccasion,
  type Occasion,
} from './occasion';

// How often an open tab asks whether the ksi.sh theme changed (the backend
// reads ksi.sh every minute), and the shortest gap when the tab comes back.
const POLL_INTERVAL_MS = 5 * 60 * 1000;
const MIN_REFRESH_GAP_MS = 60 * 1000;
// An open tab that cannot reach the API drops the occasion after this long
// (the backend's own limit for an occasion it cannot confirm with ksi.sh).
const UNCONFIRMED_MAX_MS = 30 * 60 * 1000;

function readCache(): Occasion | null {
  try {
    return readCachedOccasion(localStorage.getItem(OCCASION_CACHE_KEY), Date.now());
  } catch {
    // storage blocked (privacy mode): start from the normal look
    return null;
  }
}

function writeCache(occasion: Occasion | null): void {
  try {
    localStorage.setItem(OCCASION_CACHE_KEY, cacheOccasion(occasion, Date.now()));
  } catch {
    // storage blocked or full: only the next reload starts without the theme
  }
}

// The ksi.sh occasion that is on now (null = normal look). Starts from the
// last known state, then asks the API on load, every few minutes and when
// the tab becomes visible again. A failed or malformed answer (backend just
// started, ksi.sh unreachable) keeps the current state: the backend itself
// drops an occasion it could not confirm for half an hour, and a tab that
// cannot reach the API at all drops it after UNCONFIRMED_MAX_MS.
export function useOccasion(): Occasion | null {
  const [occasion, setOccasion] = useState<Occasion | null>(readCache);

  useEffect(() => {
    let cancelled = false;
    let lastRequest = 0;
    // counted from the load: the cached state itself is at most CACHE_MAX_AGE_MS old
    let confirmedAt = Date.now();

    const refresh = async () => {
      lastRequest = Date.now();
      let next: Occasion | null | undefined;
      try {
        next = parseOccasion(await apiJson<unknown>('/occasion'));
      } catch {
        // decorative feature: an error keeps the state described above
        next = undefined;
      }
      if (cancelled) return;
      if (next === undefined) {
        if (Date.now() - confirmedAt > UNCONFIRMED_MAX_MS) setOccasion(null);
        return;
      }
      confirmedAt = Date.now();
      writeCache(next);
      setOccasion((current) => (sameOccasion(current, next) ? current : next));
    };

    const onVisibility = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastRequest >= MIN_REFRESH_GAP_MS) void refresh();
    };

    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return occasion;
}
