// Shared class names of the admin panel (KSI tokens from index.css).

export const CARD = 'rounded-card border border-line bg-surface p-4 sm:p-5';

export const SECTION_TITLE = 'font-head text-base font-semibold text-fg';

export const LABEL = 'text-sm font-semibold text-fg';

export const HINT = 'text-xs text-muted';

// inputs get the same focus ring as buttons (index.css styles only button / a)
export const INPUT =
  'w-full rounded-control border border-line-strong bg-surface px-3 py-2 text-sm text-fg ' +
  'focus:outline-none focus-visible:shadow-ring disabled:opacity-60';

export const SMALL_BUTTON =
  'inline-flex items-center gap-1.5 px-2 py-1 rounded-control text-xs font-semibold text-muted ' +
  'transition-colors hover:bg-surface-hover hover:text-fg disabled:opacity-50 disabled:cursor-not-allowed';

export const BADGE = 'inline-flex items-center rounded-control border px-1.5 py-0.5 text-[11px] font-semibold';
