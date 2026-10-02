import { useCallback, useEffect, useState } from 'react';
import { isSessionLost } from '../../lib/api';

type Outcome<T> =
  | { source: () => Promise<T>; attempt: number; ok: true; value: T }
  | { source: () => Promise<T>; attempt: number; ok: false };

export interface Loader<T> {
  // last loaded value (kept while a newer request is loading)
  data: T | null;
  isLoading: boolean;
  hasError: boolean;
  reload: () => void;
  // local change of the loaded value (e.g. an item after a successful PATCH)
  update: (change: (value: T) => T) => void;
}

// Loads data with `load` (memoize it with useCallback - a new function means a
// new request). Results of outdated requests are ignored; a lost session is
// handled globally (useAuth), so it is not shown as a load error.
export function useLoader<T>(load: () => Promise<T>): Loader<T> {
  const [attempt, setAttempt] = useState(0);
  const [outcome, setOutcome] = useState<Outcome<T> | null>(null);

  useEffect(() => {
    let cancelled = false;
    load().then(
      (value) => {
        if (!cancelled) setOutcome({ source: load, attempt, ok: true, value });
      },
      (error: unknown) => {
        if (!cancelled && !isSessionLost(error)) setOutcome({ source: load, attempt, ok: false });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const update = useCallback((change: (value: T) => T) => {
    setOutcome((prev) => (prev !== null && prev.ok ? { ...prev, value: change(prev.value) } : prev));
  }, []);

  const isCurrent = outcome !== null && outcome.source === load && outcome.attempt === attempt;
  return {
    data: outcome !== null && outcome.ok ? outcome.value : null,
    isLoading: !isCurrent,
    hasError: isCurrent && !outcome.ok,
    reload,
    update,
  };
}
