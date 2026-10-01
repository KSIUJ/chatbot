import { useCallback, useEffect, useRef, useState } from 'react';

// Tailwind's `md` breakpoint: from here the sidebar is always visible.
const DESKTOP_QUERY = '(min-width: 48rem)';

// Off-canvas sidebar on small screens: Escape closes it, focus moves into it
// on open and back to the menu button on close, the page does not scroll
// behind it, and it closes by itself once the screen becomes desktop-wide.
export function useDrawer() {
  const [isOpen, setIsOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  // focus goes back only after the drawer was actually open
  const wasOpenRef = useRef(false);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    if (isOpen) {
      closeButtonRef.current?.focus();
    } else if (wasOpenRef.current) {
      menuButtonRef.current?.focus();
    }
    wasOpenRef.current = isOpen;
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // window, not document: an open settings popover handles Escape first
    // (it calls preventDefault) and only that popover closes
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) setIsOpen(false);
    };
    const desktop = window.matchMedia(DESKTOP_QUERY);
    const handleViewport = () => {
      if (desktop.matches) setIsOpen(false);
    };
    window.addEventListener('keydown', handleKey);
    desktop.addEventListener('change', handleViewport);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKey);
      desktop.removeEventListener('change', handleViewport);
    };
  }, [isOpen]);

  return { isOpen, open, close, menuButtonRef, closeButtonRef };
}
