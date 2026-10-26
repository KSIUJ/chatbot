import { useCallback, useEffect, useState } from 'react';
import { disconnectUsos, fetchUsosStatus, startUsosConnect, withoutLink, type UsosStatus } from './usos';

// idle -> connecting (until the browser leaves for USOS)
// idle -> confirmDisconnect -> disconnecting -> idle
export type UsosPhase = 'idle' | 'connecting' | 'confirmDisconnect' | 'disconnecting';
export type UsosActionError = 'connect' | 'disconnect';

export interface UsosState {
  // null while loading or when the status could not be read (item hidden)
  status: UsosStatus | null;
  phase: UsosPhase;
  error: UsosActionError | null;
  connect: () => void;
  askDisconnect: () => void;
  cancelDisconnect: () => void;
  disconnect: () => void;
}

export function useUsos(): UsosState {
  const [status, setStatus] = useState<UsosStatus | null>(null);
  const [phase, setPhase] = useState<UsosPhase>('idle');
  const [error, setError] = useState<UsosActionError | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchUsosStatus().then(
      (next) => {
        if (!cancelled) setStatus(next);
      },
      () => {
        // an older backend or an outage: no USOS item
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const connect = useCallback(() => {
    setPhase('connecting');
    setError(null);
    startUsosConnect().then(
      (url) => window.location.assign(url),
      () => {
        setPhase('idle');
        setError('connect');
      },
    );
  }, []);

  const askDisconnect = useCallback(() => {
    setError(null);
    setPhase('confirmDisconnect');
  }, []);

  const cancelDisconnect = useCallback(() => setPhase('idle'), []);

  const disconnect = useCallback(() => {
    setPhase('disconnecting');
    disconnectUsos().then(
      () => {
        setStatus((previous) => (previous === null ? null : withoutLink(previous)));
        setPhase('idle');
      },
      () => {
        setPhase('idle');
        setError('disconnect');
      },
    );
  }, []);

  return { status, phase, error, connect, askDisconnect, cancelDisconnect, disconnect };
}
