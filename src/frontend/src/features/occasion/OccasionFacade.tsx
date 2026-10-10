import { useState, type ReactNode } from 'react';

interface OccasionFacadeProps {
  // from facadeUrl(); null = no facade for this occasion
  src: string | null;
  // "login": fixed along the bottom of the login screen; "chat": a band at
  // the bottom of an empty conversation
  variant: 'login' | 'chat';
  // shown instead when there is no facade or it fails to load
  fallback?: ReactNode;
}

// The WMiI UJ building as ksi.sh draws it for the current occasion. Purely
// decorative: hidden from screen readers, replaced by `fallback` if the image
// fails to load (e.g. the occasion ended while the tab was open).
export default function OccasionFacade({ src, variant, fallback = null }: OccasionFacadeProps) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (src === null || failedSrc === src) return fallback;

  return (
    <div className={`ksi-occasion-facade ksi-occasion-facade--${variant}`} aria-hidden="true">
      <img src={src} alt="" decoding="async" draggable={false} onError={() => setFailedSrc(src)} />
    </div>
  );
}
