import { describe, expect, it } from 'vitest';
import { LANGUAGES, translations } from '../preferences/languages';
import type { AttachmentProblem } from './attachments';
import { describeAttachmentProblem } from './attachmentText';

const PROBLEMS: AttachmentProblem[] = [
  { code: 'too_large', name: 'a.pdf', maxMb: 10 },
  { code: 'too_large' },
  { code: 'empty', name: 'a.txt' },
  { code: 'unsupported_type', name: 'a.exe' },
  { code: 'unreadable', name: 'a.pdf' },
  { code: 'upload_failed', name: 'a.pdf' },
  { code: 'images_unsupported' },
  { code: 'too_many', maxFiles: 5 },
  { code: 'daily_limit', limit: 20, resetAt: '2026-10-02T22:00:00+00:00' },
  { code: 'disabled' },
  { code: 'not_found' },
  { code: 'chat_disabled' },
  { code: 'upload_timeout', name: 'a.pdf' },
  { code: 'busy' },
  { code: 'storage_full' },
  { code: 'storage_unavailable' },
];

describe('describeAttachmentProblem', () => {
  it('names the file and the limit', () => {
    const text = describeAttachmentProblem({ code: 'too_large', name: 'plan.pdf', maxMb: 10 }, translations.en);

    expect(text).toBe('plan.pdf is too large (limit 10 MB).');
  });

  it('works without a file name or a known limit', () => {
    expect(describeAttachmentProblem({ code: 'too_large' }, translations.pl)).toBe('Plik jest za duży.');
  });

  it.each(LANGUAGES)('has a non-empty text for every problem in %s', (code) => {
    const now = new Date('2026-10-02T20:00:00Z');
    for (const problem of PROBLEMS) {
      expect(describeAttachmentProblem(problem, translations[code], now).trim()).not.toBe('');
    }
  });
});
