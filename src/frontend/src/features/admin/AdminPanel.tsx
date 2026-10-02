import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { ArrowLeft } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import DiagnosticsTab from './DiagnosticsTab';
import IncidentsTab from './IncidentsTab';
import LimitsTab from './LimitsTab';
import ReportsTab from './ReportsTab';
import { ADMIN_TABS, tabForKey, type AdminTab } from './tabs';

interface AdminPanelProps {
  lang: Translation;
  onClose: () => void;
}

function TabContent({ tab, lang }: { tab: AdminTab; lang: Translation }) {
  switch (tab) {
    case 'limits':
      return <LimitsTab lang={lang} />;
    case 'reports':
      return <ReportsTab lang={lang} />;
    case 'incidents':
      return <IncidentsTab lang={lang} />;
    case 'diagnostics':
      return <DiagnosticsTab lang={lang} />;
  }
}

// Full-screen admin view over the chat (the chat stays mounted underneath, so
// an answer being streamed is not lost). Tabs follow the WAI-ARIA tabs pattern;
// the server checks the admin group on every request anyway.
export default function AdminPanel({ lang, onClose }: AdminPanelProps) {
  const text = lang.admin;
  const [tab, setTab] = useState<AdminTab>('limits');
  const headingRef = useRef<HTMLHeadingElement>(null);
  const tabRefs = useRef(new Map<AdminTab, HTMLButtonElement>());
  const baseId = useId();
  const tabId = (value: AdminTab) => `${baseId}-tab-${value}`;
  const panelId = `${baseId}-panel`;

  // the view replaces the whole screen: start reading from its title
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  const handleTabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const next = tabForKey(tab, event.key);
    if (next === null) return;
    event.preventDefault();
    setTab(next);
    tabRefs.current.get(next)?.focus();
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-page text-fg font-sans">
      <header className="flex items-center gap-3 px-3 sm:px-4 py-2.5 border-b border-line bg-surface">
        <button type="button" onClick={onClose} className="ksi-btn ksi-btn-secondary px-2.5 sm:px-4" aria-label={text.backToChat}>
          <ArrowLeft size={16} aria-hidden="true" />
          <span className="max-sm:hidden">{text.backToChat}</span>
        </button>
        <h1 ref={headingRef} tabIndex={-1} className="font-head text-title font-semibold truncate focus:outline-none">
          {text.title}
        </h1>
      </header>

      <div role="tablist" aria-label={text.sections} className="flex gap-1 px-3 sm:px-4 border-b border-line bg-surface overflow-x-auto overflow-y-hidden [scrollbar-width:thin]">
        {ADMIN_TABS.map((value) => {
          const isActive = value === tab;
          return (
            <button
              key={value}
              ref={(node) => {
                if (node !== null) tabRefs.current.set(value, node);
                else tabRefs.current.delete(value);
              }}
              id={tabId(value)}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={panelId}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setTab(value)}
              onKeyDown={handleTabKey}
              className={`shrink-0 px-3 py-2.5 border-b-2 text-sm font-medium transition-colors ${
                isActive ? 'border-accent text-fg' : 'border-transparent text-muted hover:text-fg'
              }`}
            >
              {text.tabs[value]}
            </button>
          );
        })}
      </div>

      <div id={panelId} role="tabpanel" aria-labelledby={tabId(tab)} className="flex-1 min-h-0 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-3 py-4 sm:p-6">
          <TabContent key={tab} tab={tab} lang={lang} />
        </div>
      </div>
    </div>
  );
}
