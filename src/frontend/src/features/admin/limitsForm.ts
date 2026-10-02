import type { AdminUser, AttachmentType, LimitChoice, LimitSettings, NumberRange, SettingsRanges } from './adminApi';

// Form state of the global limits: number fields stay strings while typing
// (an emptied field must not jump to 0).
export interface LimitsDraft {
  dailyQuestionLimit: string;
  maxFileMb: string;
  maxFilesPerMessage: string;
  maxPerDay: string;
  allowedTypes: AttachmentType[];
}

export function toDraft(settings: LimitSettings): LimitsDraft {
  const { attachments } = settings;
  return {
    dailyQuestionLimit: String(settings.dailyQuestionLimit),
    maxFileMb: String(attachments.maxFileMb),
    maxFilesPerMessage: String(attachments.maxFilesPerMessage),
    maxPerDay: String(attachments.maxPerDay),
    allowedTypes: [...attachments.allowedTypes],
  };
}

// Whole number within the range, or null.
export function parseBounded(value: string, range: NumberRange): number | null {
  const text = value.trim();
  if (!/^\d+$/.test(text)) return null;
  const number = Number(text);
  return number >= range.min && number <= range.max ? number : null;
}

// Settings to save, or null while any field is invalid (the form shows why).
export function fromDraft(draft: LimitsDraft, ranges: SettingsRanges): LimitSettings | null {
  const daily = parseBounded(draft.dailyQuestionLimit, ranges.dailyQuestionLimit);
  const maxFileMb = parseBounded(draft.maxFileMb, ranges.maxFileMb);
  const maxFiles = parseBounded(draft.maxFilesPerMessage, ranges.maxFilesPerMessage);
  const maxPerDay = parseBounded(draft.maxPerDay, ranges.maxPerDay);
  if (daily === null || maxFileMb === null || maxFiles === null || maxPerDay === null) return null;
  if (draft.allowedTypes.length === 0) return null;
  return {
    dailyQuestionLimit: daily,
    attachments: { maxFileMb, maxFilesPerMessage: maxFiles, maxPerDay, allowedTypes: [...draft.allowedTypes] },
  };
}

// Checkbox toggle that keeps the order of `available`.
export function toggleType(
  selected: readonly AttachmentType[],
  type: AttachmentType,
  available: readonly AttachmentType[],
): AttachmentType[] {
  const next = new Set(selected);
  if (next.has(type)) next.delete(type);
  else next.add(type);
  return available.filter((t) => next.has(t));
}

// Starting point of the per-user editor: the current exception or the global limit.
export function initialChoice(user: AdminUser, globalLimit: number): LimitChoice {
  const { override } = user;
  if (override === null) return { mode: 'global', dailyLimit: globalLimit, note: '' };
  return {
    mode: override.unlimited ? 'unlimited' : 'custom',
    dailyLimit: override.dailyLimit ?? globalLimit,
    note: override.note ?? '',
  };
}
