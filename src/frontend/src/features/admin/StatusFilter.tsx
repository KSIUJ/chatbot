import { useId } from 'react';
import type { AdminTranslation } from '../preferences/languages';
import { REVIEW_STATUSES, type ReviewStatus } from './adminApi';
import { INPUT, LABEL } from './styles';

interface StatusFilterProps {
  text: AdminTranslation;
  // null = all statuses
  value: ReviewStatus | null;
  onChange: (value: ReviewStatus | null) => void;
}

const ALL = 'all';

export default function StatusFilter({ text, value, onChange }: StatusFilterProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={LABEL}>
        {text.status}
      </label>
      <select
        id={id}
        value={value ?? ALL}
        onChange={(event) => {
          const next = REVIEW_STATUSES.find((status) => status === event.target.value);
          onChange(next ?? null);
        }}
        className={`${INPUT} w-auto min-w-40`}
      >
        <option value={ALL}>{text.allStatuses}</option>
        {REVIEW_STATUSES.map((status) => (
          <option key={status} value={status}>
            {text.statuses[status]}
          </option>
        ))}
      </select>
    </div>
  );
}
