import { useCallback, useState, type ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';
import type { Translation } from '../preferences/languages';
import { fetchDiagnostics, type Diagnostics, type Metric } from './adminApi';
import { LoadError, LoadingRow } from './AdminCommon';
import { EMPTY, formatBytes, formatDateTime, formatDuration, formatLatency, formatNumber } from './format';
import { CARD, HINT, SECTION_TITLE } from './styles';
import { useLoader } from './useLoader';

interface DiagnosticsTabProps {
  lang: Translation;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-1.5 border-b border-line last:border-b-0">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="text-sm font-semibold text-fg tabular-nums text-right break-all">{children}</dd>
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={CARD}>
      <h2 className={`${SECTION_TITLE} mb-2`}>{title}</h2>
      <dl>{children}</dl>
    </section>
  );
}

// A value or "unavailable" with the reason (from the server) underneath.
function MetricValue<T>({ metric, unavailable, format }: {
  metric: Metric<T>;
  unavailable: string;
  format: (value: T) => string;
}) {
  if (metric.value !== null) return <>{format(metric.value)}</>;
  return (
    <span className="flex flex-col items-end">
      <span className="text-muted font-normal">{unavailable}</span>
      {metric.error !== null && <span className="text-xs font-normal text-danger-text break-words">{metric.error}</span>}
    </span>
  );
}

function DiagnosticsCards({ lang, data }: { lang: Translation; data: Diagnostics }) {
  const text = lang.admin;
  const locale = lang.htmlLang;
  const count = (value: number) => formatNumber(value, locale);
  const bytes = (value: number) => formatBytes(value, locale);
  const date = (value: string) => formatDateTime(value, locale);
  const metric = <T,>(value: Metric<T>, format: (v: T) => string) => (
    <MetricValue metric={value} unavailable={text.unavailable} format={format} />
  );
  const { llm, usage, totals, rag, storage } = data;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <Card title={text.model}>
        <Row label={text.provider}>{llm.provider}</Row>
        <Row label={text.modelName}>{llm.model}</Row>
        <Row label={text.uptime}>{formatDuration(llm.uptimeSeconds)}</Row>
        <Row label={text.calls}>{count(llm.totalCalls)}</Row>
        <Row label={text.errors}>
          <span className={llm.totalErrors > 0 ? 'text-danger-text' : ''}>{count(llm.totalErrors)}</span>
        </Row>
        <Row label={text.avgLatency}>{formatLatency(llm.avgLatencyMs, locale)}</Row>
        <Row label={text.p95Latency}>{formatLatency(llm.p95LatencyMs, locale)}</Row>
        <Row label={text.lastError}>
          {llm.lastError === null ? (
            EMPTY
          ) : (
            <span className="flex flex-col items-end">
              <span className="text-xs font-normal text-danger-text break-words">{llm.lastError}</span>
              <span className="text-xs font-normal text-muted">{formatDateTime(llm.lastErrorAt, locale)}</span>
            </span>
          )}
        </Row>
        {llm.recentCalls > 0 && <p className={`${HINT} pt-2`}>{text.recentWindow(llm.recentCalls)}</p>}
      </Card>

      <Card title={text.usage}>
        <Row label={text.questionsToday}>{metric(usage.questionsToday, count)}</Row>
        <Row label={text.questions7d}>{metric(usage.questions7d, count)}</Row>
        <Row label={text.activeToday}>{metric(usage.activeUsersToday, count)}</Row>
        <Row label={text.active7d}>{metric(usage.activeUsers7d, count)}</Row>
      </Card>

      <Card title={text.data}>
        <Row label={text.usersCount}>{metric(totals.users, count)}</Row>
        <Row label={text.conversations}>{metric(totals.conversations, count)}</Row>
        <Row label={text.messages}>{metric(totals.messages, count)}</Row>
        <Row label={text.openReports}>{metric(totals.openReports, count)}</Row>
        <Row label={text.openIncidents}>{metric(totals.openIncidents, count)}</Row>
      </Card>

      <Card title={text.ragIndex}>
        <Row label={text.vectorCount}>{metric(rag.vectorCount, count)}</Row>
        <Row label={text.lexicalCount}>{metric(rag.lexicalCount, count)}</Row>
        <Row label={text.lexicalSize}>{metric(rag.lexicalSizeBytes, bytes)}</Row>
        <Row label={text.lastIngest}>{metric(rag.lastIngestAt, date)}</Row>
      </Card>

      <Card title={text.storage}>
        <Row label={text.databaseSize}>{metric(storage.databaseSizeBytes, bytes)}</Row>
        <Row label={text.diskFree}>
          {storage.diskFreeBytes.value !== null && storage.diskTotalBytes.value !== null
            ? `${bytes(storage.diskFreeBytes.value)} / ${bytes(storage.diskTotalBytes.value)}`
            : metric(storage.diskFreeBytes, bytes)}
        </Row>
      </Card>
    </div>
  );
}

// Model status, usage, search index, database and disk; refreshed on demand.
export default function DiagnosticsTab({ lang }: DiagnosticsTabProps) {
  const text = lang.admin;
  // 0 = first load (a cached snapshot is fine); each Refresh click asks for a fresh one
  const [refreshes, setRefreshes] = useState(0);
  const load = useCallback(() => fetchDiagnostics(refreshes > 0), [refreshes]);
  const diagnostics = useLoader(load);
  const { data } = diagnostics;

  return (
    <section className="flex flex-col gap-4" aria-busy={diagnostics.isLoading}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted" aria-live="polite">
          {data !== null ? text.generatedAt(formatDateTime(data.generatedAt, lang.htmlLang)) : ''}
        </p>
        <button
          type="button"
          onClick={() => setRefreshes((n) => n + 1)}
          disabled={diagnostics.isLoading}
          className="ksi-btn ksi-btn-secondary disabled:opacity-50"
        >
          <RefreshCw size={14} className={diagnostics.isLoading ? 'animate-spin' : ''} aria-hidden="true" />
          {text.refresh}
        </button>
      </div>
      {diagnostics.hasError && <LoadError text={text} retryLabel={lang.retry} onRetry={diagnostics.reload} />}
      {diagnostics.isLoading && data === null && <LoadingRow label={lang.loading} />}
      {data !== null && <DiagnosticsCards lang={lang} data={data} />}
    </section>
  );
}
