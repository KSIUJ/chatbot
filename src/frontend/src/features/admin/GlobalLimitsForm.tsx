import { useId, useState, type FormEvent } from 'react';
import type { AdminTranslation } from '../preferences/languages';
import { saveSettings, type AdminSettings, type NumberRange } from './adminApi';
import { fromDraft, parseBounded, toDraft, toggleType, type LimitsDraft } from './limitsForm';
import { CARD, HINT, INPUT, LABEL, SECTION_TITLE } from './styles';

interface NumberFieldProps {
  label: string;
  value: string;
  range: NumberRange;
  defaultValue: number;
  text: AdminTranslation;
  disabled: boolean;
  onChange: (value: string) => void;
}

function NumberField({ label, value, range, defaultValue, text, disabled, onChange }: NumberFieldProps) {
  const id = useId();
  const hintId = useId();
  const isInvalid = parseBounded(value, range) === null;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={range.min}
        max={range.max}
        step={1}
        required
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={isInvalid || undefined}
        aria-describedby={hintId}
        className={`${INPUT} sm:max-w-40 ${isInvalid ? 'border-danger' : ''}`}
      />
      <span id={hintId} className={HINT}>
        {range.min}–{range.max} · {text.defaultValue(String(defaultValue))}
      </span>
    </div>
  );
}

interface GlobalLimitsFormProps {
  text: AdminTranslation;
  settings: AdminSettings;
  onSaved: (settings: AdminSettings) => void;
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

// Global daily question limit and attachment limits (attachments are enforced
// once the attachments feature ships; the values are stored already).
export default function GlobalLimitsForm({ text, settings, onSaved }: GlobalLimitsFormProps) {
  const [draft, setDraft] = useState<LimitsDraft>(() => toDraft(settings));
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const typesId = useId();
  const { ranges, defaults } = settings;
  const isSaving = saveState === 'saving';
  const valid = fromDraft(draft, ranges);

  const change = (patch: Partial<LimitsDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setSaveState('idle');
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (valid === null || isSaving) return;
    setSaveState('saving');
    try {
      const saved = await saveSettings(valid);
      setDraft(toDraft(saved));
      setSaveState('saved');
      onSaved(saved);
    } catch {
      setSaveState('error');
    }
  };

  const field = (label: string, key: Exclude<keyof LimitsDraft, 'allowedTypes'>, range: NumberRange, fallback: number) => (
    <NumberField
      label={label}
      value={draft[key]}
      range={range}
      defaultValue={fallback}
      text={text}
      disabled={isSaving}
      onChange={(value) => change({ [key]: value })}
    />
  );

  return (
    <form onSubmit={(event) => void handleSubmit(event)} className={`${CARD} flex flex-col gap-5`} noValidate>
      <h2 className={SECTION_TITLE}>{text.globalLimits}</h2>

      {field(text.dailyQuestionLimit, 'dailyQuestionLimit', ranges.dailyQuestionLimit, defaults.dailyQuestionLimit)}

      <fieldset className="flex flex-col gap-4 border-t border-line pt-4" disabled={isSaving}>
        <legend className="sr-only">{text.attachments}</legend>
        <div>
          <h3 className="text-sm font-semibold text-fg" aria-hidden="true">{text.attachments}</h3>
          <p className={HINT}>{text.attachmentsNote}</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {field(text.maxFileMb, 'maxFileMb', ranges.maxFileMb, defaults.attachments.maxFileMb)}
          {field(text.maxFilesPerMessage, 'maxFilesPerMessage', ranges.maxFilesPerMessage, defaults.attachments.maxFilesPerMessage)}
          {field(text.maxAttachmentsPerDay, 'maxPerDay', ranges.maxPerDay, defaults.attachments.maxPerDay)}
        </div>
        <div role="group" aria-labelledby={typesId} className="flex flex-col gap-2">
          <span id={typesId} className={LABEL}>
            {text.allowedTypes}
          </span>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {settings.availableTypes.map((type) => (
              <label key={type} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={draft.allowedTypes.includes(type)}
                  onChange={() => change({ allowedTypes: toggleType(draft.allowedTypes, type, settings.availableTypes) })}
                  className="size-4 accent-accent"
                />
                {text.typeNames[type]}
              </label>
            ))}
          </div>
        </div>
      </fieldset>

      <div className="flex flex-wrap items-center justify-end gap-3">
        <p role="status" className={`text-label ${saveState === 'error' ? 'text-danger-text' : 'text-muted'}`}>
          {saveState === 'saved' ? text.saved : saveState === 'error' ? text.saveError : ''}
        </p>
        <button type="submit" disabled={valid === null || isSaving} className="ksi-btn ksi-btn-primary disabled:opacity-50">
          {text.save}
        </button>
      </div>
    </form>
  );
}
