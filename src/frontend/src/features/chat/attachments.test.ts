import { describe, expect, it } from 'vitest';
import { ApiRequestError } from '../../lib/api';
import {
  acceptList,
  attachmentProblemOf,
  checkFiles,
  formatFileSize,
  kindOfFile,
  parseAttachmentLimits,
  parseAttachmentList,
  type AttachmentLimits,
} from './attachments';

const LIMITS: AttachmentLimits = {
  maxFileMb: 10,
  maxImageMb: 5,
  maxFilesPerMessage: 3,
  maxPerDay: 20,
  usedToday: 0,
  allowedTypes: ['pdf', 'docx', 'txt', 'png', 'jpeg', 'webp'],
  imagesSupported: true,
};

const MB = 1024 * 1024;

function file(name: string, size: number, type = ''): { name: string; size: number; type: string } {
  return { name, size, type };
}

describe('parseAttachmentLimits', () => {
  it('reads the attachments block of /usage', () => {
    expect(
      parseAttachmentLimits({
        max_file_mb: 10,
        max_image_mb: 5,
        max_files_per_message: 5,
        max_per_day: 20,
        used_today: 2,
        allowed_types: ['pdf', 'jpeg', 'gif'],
        images_supported: false,
      }),
    ).toEqual({
      maxFileMb: 10,
      maxImageMb: 5,
      maxFilesPerMessage: 5,
      maxPerDay: 20,
      usedToday: 2,
      // unknown types are dropped
      allowedTypes: ['pdf', 'jpeg'],
      imagesSupported: false,
    });
  });

  it('rejects malformed blocks', () => {
    expect(parseAttachmentLimits(undefined)).toBeNull();
    expect(parseAttachmentLimits({ max_file_mb: '10' })).toBeNull();
  });
});

describe('parseAttachmentList', () => {
  it('keeps valid entries only', () => {
    expect(
      parseAttachmentList([
        { id: 'a', name: 'plan.pdf', size: 10, type: 'pdf' },
        { id: 'b', name: 'x', size: -1, type: 'pdf' },
        { id: 'c', name: 'y', size: 1, type: 'exe' },
        'junk',
      ]),
    ).toEqual([{ id: 'a', name: 'plan.pdf', size: 10, type: 'pdf' }]);
    expect(parseAttachmentList(undefined)).toEqual([]);
  });
});

describe('kindOfFile', () => {
  it.each([
    ['Plan.PDF', '', 'pdf'],
    ['notes.txt', '', 'txt'],
    ['photo.jpg', '', 'jpeg'],
    ['photo.jpeg', '', 'jpeg'],
    ['image', 'image/png', 'png'],
    ['doc.docx', '', 'docx'],
    ['virus.exe', 'application/x-msdownload', null],
    ['anim.gif', 'image/gif', null],
  ])('%s (%s) -> %s', (name, type, expected) => {
    expect(kindOfFile(file(name, 1, type))).toBe(expected);
  });
});

describe('acceptList', () => {
  it('lists extensions of the allowed types', () => {
    expect(acceptList(LIMITS)).toBe('.pdf,.docx,.txt,.png,.jpg,.jpeg,.webp');
  });

  it('leaves images out when the model cannot see them', () => {
    expect(acceptList({ ...LIMITS, imagesSupported: false })).toBe('.pdf,.docx,.txt');
  });
});

describe('checkFiles', () => {
  it('accepts files within the limits', () => {
    const files = [file('a.pdf', MB), file('b.png', MB)];

    expect(checkFiles(files, 0, LIMITS)).toEqual({ accepted: files, problems: [] });
  });

  it('rejects too large, empty and unsupported files with their names', () => {
    const result = checkFiles(
      [file('big.pdf', 10 * MB + 1), file('big.png', 5 * MB + 1), file('empty.txt', 0), file('x.exe', 5)],
      0,
      LIMITS,
    );

    expect(result.accepted).toEqual([]);
    expect(result.problems).toEqual([
      { code: 'too_large', name: 'big.pdf', maxMb: 10 },
      { code: 'too_large', name: 'big.png', maxMb: 5 },
      { code: 'empty', name: 'empty.txt' },
      { code: 'unsupported_type', name: 'x.exe' },
    ]);
  });

  it('rejects types switched off by the admins', () => {
    const result = checkFiles([file('a.docx', 5)], 0, { ...LIMITS, allowedTypes: ['pdf'] });

    expect(result.problems).toEqual([{ code: 'unsupported_type', name: 'a.docx' }]);
  });

  it('rejects images when the model cannot see them', () => {
    const result = checkFiles([file('a.png', 5)], 0, { ...LIMITS, imagesSupported: false });

    expect(result.problems).toEqual([{ code: 'images_unsupported', name: 'a.png' }]);
  });

  it('keeps only as many files as fit in one message', () => {
    const files = [file('1.txt', 1), file('2.txt', 1), file('3.txt', 1)];

    const result = checkFiles(files, 1, LIMITS);

    expect(result.accepted).toEqual(files.slice(0, 2));
    expect(result.problems).toEqual([{ code: 'too_many', maxFiles: 3 }]);
  });

  it('refuses everything when attachments are switched off', () => {
    const result = checkFiles([file('a.txt', 1)], 0, { ...LIMITS, maxPerDay: 0 });

    expect(result).toEqual({ accepted: [], problems: [{ code: 'disabled' }] });
  });
});

describe('formatFileSize', () => {
  it.each([
    [0, '0 B'],
    [900, '900 B'],
    [1536, '1.5 KB'],
    [10 * MB, '10 MB'],
    [2.25 * MB, '2.3 MB'],
  ])('%d bytes -> %s', (bytes, expected) => {
    expect(formatFileSize(bytes, 'en')).toBe(expected);
  });

  it('uses the locale decimal separator', () => {
    expect(formatFileSize(1536, 'pl')).toBe('1,5 KB');
  });
});

describe('attachmentProblemOf', () => {
  it('maps server codes', () => {
    const tooLarge = new ApiRequestError(413, null, { code: 'file_too_large', max_mb: 10 });
    const limited = new ApiRequestError(429, null, {
      code: 'attachments_limited',
      limit: 20,
      reset_at: '2026-10-02T22:00:00+00:00',
    });

    expect(attachmentProblemOf(tooLarge, 'a.pdf')).toEqual({ code: 'too_large', name: 'a.pdf', maxMb: 10 });
    expect(attachmentProblemOf(limited, 'a.pdf')).toEqual({
      code: 'daily_limit',
      limit: 20,
      resetAt: '2026-10-02T22:00:00+00:00',
    });
    expect(attachmentProblemOf(new ApiRequestError(415, null, { code: 'unsupported_type' }), 'x')).toEqual({
      code: 'unsupported_type',
      name: 'x',
    });
    expect(attachmentProblemOf(new ApiRequestError(422, null, { code: 'unreadable_file' }), 'x')).toEqual({
      code: 'unreadable',
      name: 'x',
    });
    expect(attachmentProblemOf(new ApiRequestError(422, null, { code: 'images_unsupported' }))).toEqual({
      code: 'images_unsupported',
    });
    expect(attachmentProblemOf(new ApiRequestError(422, null, { code: 'too_many_files', max_files: 5 }))).toEqual({
      code: 'too_many',
      maxFiles: 5,
    });
    expect(attachmentProblemOf(new ApiRequestError(404, null, { code: 'attachment_not_found' }))).toEqual({
      code: 'not_found',
    });
    expect(attachmentProblemOf(new ApiRequestError(403, null, { code: 'attachments_disabled' }))).toEqual({
      code: 'disabled',
    });
  });

  it('maps upload abuse limits', () => {
    expect(attachmentProblemOf(new ApiRequestError(408, null, { code: 'upload_timeout' }), 'a.pdf')).toEqual({
      code: 'upload_timeout',
      name: 'a.pdf',
    });
    expect(attachmentProblemOf(new ApiRequestError(429, null, { code: 'uploads_busy' }), 'a.pdf')).toEqual({
      code: 'busy',
    });
    expect(attachmentProblemOf(new ApiRequestError(429, null, { code: 'attachments_storage_full' }), 'a')).toEqual({
      code: 'storage_full',
    });
    expect(attachmentProblemOf(new ApiRequestError(507, null, { code: 'storage_unavailable' }), 'a')).toEqual({
      code: 'storage_unavailable',
    });
  });

  it('treats a 413 without a body (proxy limit) as too large', () => {
    expect(attachmentProblemOf(new ApiRequestError(413, null, null), 'a.pdf')).toEqual({
      code: 'too_large',
      name: 'a.pdf',
    });
  });

  it('falls back to a generic upload error', () => {
    expect(attachmentProblemOf(new Error('network'), 'a.pdf')).toEqual({ code: 'upload_failed', name: 'a.pdf' });
  });

  it('returns null for send errors unrelated to attachments', () => {
    expect(attachmentProblemOf(new ApiRequestError(429, null, { code: 'rate_limited' }))).toBeNull();
    expect(attachmentProblemOf(new ApiRequestError(500, null, null))).toBeNull();
  });
});
