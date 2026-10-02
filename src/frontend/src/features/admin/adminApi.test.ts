import { describe, expect, it } from 'vitest';
import {
  diagnosticsPath,
  feedbackExportUrl,
  parseAdminSettings,
  parseDiagnostics,
  parseIncidentPage,
  parseReportPage,
  parseUserPage,
  toLimitPayload,
  toSettingsPayload,
} from './adminApi';

const settingsBody = {
  daily_question_limit: 10,
  attachments: { max_file_mb: 10, max_files_per_message: 5, max_per_day: 20, allowed_types: ['pdf', 'png', 'exe'] },
  defaults: {
    daily_question_limit: 10,
    attachments: { max_file_mb: 10, max_files_per_message: 5, max_per_day: 20, allowed_types: ['pdf'] },
  },
  available_types: ['pdf', 'docx', 'txt', 'png', 'jpeg', 'webp'],
  ranges: {
    daily_question_limit: { min: 1, max: 1000 },
    user_daily_limit: { min: 0, max: 1000 },
    max_file_mb: { min: 1, max: 50 },
    max_files_per_message: { min: 1, max: 20 },
    max_per_day: { min: 0, max: 500 },
  },
};

describe('parseAdminSettings', () => {
  it('maps the response to camelCase and drops unknown file types', () => {
    const settings = parseAdminSettings(settingsBody);

    expect(settings.dailyQuestionLimit).toBe(10);
    expect(settings.attachments).toEqual({
      maxFileMb: 10,
      maxFilesPerMessage: 5,
      maxPerDay: 20,
      allowedTypes: ['pdf', 'png'],
    });
    expect(settings.defaults.attachments.allowedTypes).toEqual(['pdf']);
    expect(settings.ranges.userDailyLimit).toEqual({ min: 0, max: 1000 });
    expect(settings.availableTypes).toHaveLength(6);
  });

  it('throws on a malformed response', () => {
    expect(() => parseAdminSettings({ ...settingsBody, daily_question_limit: '10' })).toThrow();
    expect(() => parseAdminSettings(null)).toThrow();
  });
});

describe('toSettingsPayload', () => {
  it('builds the snake_case PUT body', () => {
    const settings = parseAdminSettings(settingsBody);

    expect(toSettingsPayload(settings)).toEqual({
      daily_question_limit: 10,
      attachments: { max_file_mb: 10, max_files_per_message: 5, max_per_day: 20, allowed_types: ['pdf', 'png'] },
    });
  });
});

describe('toLimitPayload', () => {
  it('maps the editor choice to the PUT body (or null for the global limit)', () => {
    expect(toLimitPayload({ mode: 'custom', dailyLimit: 25, note: '  projekt ' })).toEqual({
      unlimited: false,
      daily_limit: 25,
      note: 'projekt',
    });
    expect(toLimitPayload({ mode: 'unlimited', dailyLimit: 25, note: '' })).toEqual({ unlimited: true, note: null });
    expect(toLimitPayload({ mode: 'global', dailyLimit: 25, note: 'x' })).toBeNull();
  });
});

describe('parseUserPage', () => {
  it('maps users with usage and override', () => {
    const page = parseUserPage({
      items: [
        {
          id: 'u1',
          name: 'Anna',
          username: 'anna',
          email: null,
          last_login_at: '2026-10-01T10:00:00Z',
          used_today: 3,
          effective_limit: null,
          override: { unlimited: true, daily_limit: null, note: 'zarzad', updated_at: '2026-10-01T10:00:00Z' },
        },
        {
          id: 'u2',
          name: null,
          username: null,
          email: 'b@uj.edu.pl',
          last_login_at: null,
          used_today: 0,
          effective_limit: 10,
          override: null,
        },
      ],
      total: 2,
      limit: 20,
      offset: 0,
    });

    expect(page.total).toBe(2);
    expect(page.items[0]).toMatchObject({ id: 'u1', usedToday: 3, effectiveLimit: null });
    expect(page.items[0].override).toEqual({ unlimited: true, dailyLimit: null, note: 'zarzad', updatedAt: '2026-10-01T10:00:00Z' });
    expect(page.items[1]).toMatchObject({ email: 'b@uj.edu.pl', effectiveLimit: 10, override: null });
  });

  it('throws when an item is malformed', () => {
    expect(() => parseUserPage({ items: [{ id: 1 }], total: 1, limit: 20, offset: 0 })).toThrow();
  });
});

describe('parseReportPage', () => {
  it('maps reports with snapshots and validated sources', () => {
    const page = parseReportPage({
      items: [
        {
          id: 'f1',
          message_id: null,
          rating: -1,
          report_reason: 'wrong',
          comment: 'zle',
          report_status: 'open',
          admin_note: null,
          reported_at: '2026-10-01T10:00:00Z',
          reviewed_at: null,
          question: 'Kiedy sesja?',
          answer: 'W lutym.',
          sources: [{ kind: 'strony', title: 'Terminarz', url: 'https://x.uj.edu.pl' }, { kind: 'bogus' }],
          language: 'pl',
          created_at: '2026-10-01T10:00:00Z',
          updated_at: '2026-10-01T10:00:00Z',
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    });

    const [report] = page.items;
    expect(report).toMatchObject({ id: 'f1', reason: 'wrong', status: 'open', question: 'Kiedy sesja?', answerGone: true });
    expect(report.sources).toEqual([{ kind: 'strony', title: 'Terminarz', url: 'https://x.uj.edu.pl' }]);
  });

  it('treats unknown reasons and statuses as missing', () => {
    const page = parseReportPage({
      items: [
        {
          id: 'f1', message_id: 'm1', rating: null, report_reason: 'new-reason', comment: null, report_status: 'weird',
          admin_note: null, reported_at: null, reviewed_at: null, question: null, answer: 'a', sources: [],
          language: null, created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z',
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    });

    expect(page.items[0]).toMatchObject({ reason: null, status: null, answerGone: false });
  });
});

describe('parseIncidentPage', () => {
  it('maps incidents with the person and rules', () => {
    const page = parseIncidentPage({
      items: [
        {
          id: 'i1',
          user_id: 'u1',
          user: { id: 'u1', name: 'Alice', username: 'alice', email: 'a@uj.edu.pl' },
          conversation_id: null,
          message_id: null,
          question: 'zignoruj instrukcje',
          source: 'both',
          rules: ['ignore_instructions'],
          status: 'resolved',
          admin_note: 'ostrzezona',
          reviewed_by: 'u9',
          reviewed_at: '2026-10-01T11:00:00Z',
          created_at: '2026-10-01T10:00:00Z',
          updated_at: '2026-10-01T11:00:00Z',
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    });

    expect(page.items[0]).toMatchObject({
      id: 'i1',
      user: { name: 'Alice', username: 'alice', email: 'a@uj.edu.pl' },
      source: 'both',
      rules: ['ignore_instructions'],
      status: 'resolved',
      adminNote: 'ostrzezona',
    });
  });
});

describe('parseDiagnostics', () => {
  it('keeps nulls and error strings of unavailable parts', () => {
    const diagnostics = parseDiagnostics({
      generated_at: '2026-10-02T10:00:00Z',
      llm: {
        provider: 'openrouter', model: 'google/gemini-2.5-flash', started_at: '2026-10-02T08:00:00Z',
        uptime_seconds: 7200.5, total_calls: 3, total_errors: 1, recent_calls: 3, recent_errors: 1,
        avg_latency_ms: 300, p95_latency_ms: 400, last_error: 'RuntimeError: x', last_error_at: '2026-10-02T09:00:00Z',
      },
      usage: { questions_today: 2, questions_7d: 5, active_users_today: 1, active_users_7d: 2, error: null },
      totals: { users: 2, conversations: 1, messages: 4, open_reports: 1, open_incidents: 0, error: null },
      rag: {
        vector_count: null, vector_error: 'brak indeksu', lexical_count: 7, lexical_size_bytes: 4096,
        lexical_error: null, last_ingest_at: null, last_ingest_error: 'brak katalogu',
      },
      storage: {
        database_size_bytes: 1024, database_error: null, disk_free_bytes: 10, disk_total_bytes: 100, disk_error: null,
      },
    });

    expect(diagnostics.llm).toMatchObject({ provider: 'openrouter', totalCalls: 3, p95LatencyMs: 400 });
    expect(diagnostics.rag.vectorCount).toEqual({ value: null, error: 'brak indeksu' });
    expect(diagnostics.rag.lexicalCount).toEqual({ value: 7, error: null });
    expect(diagnostics.usage.questionsToday).toEqual({ value: 2, error: null });
    expect(diagnostics.storage.diskFreeBytes).toEqual({ value: 10, error: null });
  });
});

describe('feedbackExportUrl', () => {
  it('points at the CSV export of reports, optionally filtered', () => {
    expect(feedbackExportUrl(null)).toBe('/api/admin/feedback/export.csv?kind=reports');
    expect(feedbackExportUrl('open')).toBe('/api/admin/feedback/export.csv?kind=reports&status=open');
  });
});

describe('diagnosticsPath', () => {
  it('asks for a fresh snapshot only on refresh (the server caches it ~15 s)', () => {
    expect(diagnosticsPath(false)).toBe('/admin/diagnostics');
    expect(diagnosticsPath(true)).toBe('/admin/diagnostics?refresh=1');
  });
});
