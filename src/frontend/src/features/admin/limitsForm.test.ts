import { describe, expect, it } from 'vitest';
import type { AdminUser, LimitSettings, SettingsRanges } from './adminApi';
import { fromDraft, initialChoice, parseBounded, toDraft, toggleType } from './limitsForm';

const RANGES: SettingsRanges = {
  dailyQuestionLimit: { min: 1, max: 1000 },
  userDailyLimit: { min: 0, max: 1000 },
  maxFileMb: { min: 1, max: 50 },
  maxFilesPerMessage: { min: 1, max: 20 },
  maxPerDay: { min: 0, max: 500 },
};

const SETTINGS: LimitSettings = {
  dailyQuestionLimit: 10,
  attachments: { maxFileMb: 10, maxFilesPerMessage: 5, maxPerDay: 20, allowedTypes: ['pdf', 'png'] },
};

const USER: AdminUser = {
  id: 'u1',
  name: 'Anna',
  username: 'anna',
  email: null,
  lastLoginAt: null,
  usedToday: 0,
  effectiveLimit: 10,
  override: null,
};

describe('parseBounded', () => {
  it('accepts whole numbers within the range only', () => {
    expect(parseBounded(' 15 ', { min: 1, max: 20 })).toBe(15);
    expect(parseBounded('0', { min: 1, max: 20 })).toBeNull();
    expect(parseBounded('21', { min: 1, max: 20 })).toBeNull();
    expect(parseBounded('1.5', { min: 1, max: 20 })).toBeNull();
    expect(parseBounded('', { min: 1, max: 20 })).toBeNull();
    expect(parseBounded('-3', { min: 0, max: 20 })).toBeNull();
  });
});

describe('toDraft / fromDraft', () => {
  it('round-trips the settings', () => {
    expect(fromDraft(toDraft(SETTINGS), RANGES)).toEqual(SETTINGS);
  });

  it('gives null for an invalid field or no file types', () => {
    expect(fromDraft({ ...toDraft(SETTINGS), maxFileMb: '500' }, RANGES)).toBeNull();
    expect(fromDraft({ ...toDraft(SETTINGS), dailyQuestionLimit: '' }, RANGES)).toBeNull();
    expect(fromDraft({ ...toDraft(SETTINGS), allowedTypes: [] }, RANGES)).toBeNull();
  });
});

describe('toggleType', () => {
  it('adds and removes keeping the order of available types', () => {
    const available = ['pdf', 'docx', 'png'] as const;

    expect(toggleType(['png'], 'pdf', available)).toEqual(['pdf', 'png']);
    expect(toggleType(['pdf', 'png'], 'pdf', available)).toEqual(['png']);
  });
});

describe('initialChoice', () => {
  it('starts from the global limit without an exception', () => {
    expect(initialChoice(USER, 10)).toEqual({ mode: 'global', dailyLimit: 10, note: '' });
  });

  it('starts from the current exception', () => {
    const custom = { ...USER, override: { unlimited: false, dailyLimit: 3, note: 'x', updatedAt: '2026-10-01T00:00:00Z' } };
    const unlimited = { ...USER, override: { unlimited: true, dailyLimit: null, note: null, updatedAt: '2026-10-01T00:00:00Z' } };

    expect(initialChoice(custom, 10)).toEqual({ mode: 'custom', dailyLimit: 3, note: 'x' });
    expect(initialChoice(unlimited, 10)).toEqual({ mode: 'unlimited', dailyLimit: 10, note: '' });
  });
});
