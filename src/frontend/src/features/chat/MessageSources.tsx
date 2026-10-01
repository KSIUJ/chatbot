import { useId, useState } from 'react';
import { ChevronDown, FileText, Globe, User, type LucideIcon } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import type { ThemeStyle } from '../preferences/themes';
import { sourceHref, type Source, type SourceKind } from './sources';

const KIND_ICONS: Record<SourceKind, LucideIcon> = {
  strony: Globe,
  usos: User,
  mordor: FileText,
};

interface MessageSourcesProps {
  t: ThemeStyle;
  lang: Translation;
  sources: readonly Source[];
}

// Collapsed "Sources (n)" toggle under a bot answer.
export default function MessageSources({ t, lang, sources }: MessageSourcesProps) {
  const [isOpen, setIsOpen] = useState(false);
  const listId = useId();

  return (
    <div className="self-start max-w-full text-xs">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-controls={listId}
        className={`flex items-center gap-1 p-1.5 rounded-md font-medium ${t.textMuted} ${t.hover}`}
      >
        <ChevronDown size={14} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
        {lang.sources(sources.length)}
      </button>

      <ul id={listId} hidden={!isOpen} className="mt-1 space-y-1 pl-1.5">
        {sources.map((source, index) => {
          const Icon = KIND_ICONS[source.kind];
          const kindName = lang.sourceKinds[source.kind];
          const href = sourceHref(source);
          return (
            <li key={`${index}-${source.title}`} className={`flex items-center gap-2 min-w-0 ${t.textMuted}`}>
              <span className="shrink-0" title={kindName}>
                <Icon size={14} aria-hidden="true" />
                <span className="sr-only">{kindName}:</span>
              </span>
              {href === null ? (
                <span className="truncate" title={source.title}>{source.title}</span>
              ) : (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={source.title}
                  className={`truncate underline underline-offset-2 hover:opacity-80 ${t.text}`}
                >
                  {source.title}
                </a>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
