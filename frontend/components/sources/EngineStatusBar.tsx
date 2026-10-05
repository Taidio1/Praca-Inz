'use client';

import React, { useEffect, useState } from 'react';
import * as api from '@/lib/api';
import type { EngineStatus } from '@/lib/types';
import { formatTime, MONO } from '@/lib/format';

const STALE_MS = 60 * 60 * 1000; // brak cyklu przez godzinę = silnik nie działa

const errorLine: React.CSSProperties = {
  fontSize: 10.5,
  color: 'var(--neg)',
  fontFamily: MONO,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

/* Pasek stanu silnika: kiedy był ostatni cykl, ile pobrał, które źródła zawodzą. */
export default function EngineStatusBar() {
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await api.getEngineStatus();
        if (cancelled) return;
        setStatus(s);
        setError(false);
      } catch {
        if (!cancelled) setError(true);
      }
    };
    void load();
    const id = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const cycle = status?.last_cycle ?? null;
  const ingest = cycle?.stats.ingest;
  const stale = !cycle || Date.now() - new Date(cycle.started_at).getTime() > STALE_MS;

  let text: string;
  if (error) text = 'Nie udało się pobrać stanu silnika.';
  else if (!status) text = 'Ładowanie stanu silnika…';
  else if (!cycle) text = 'Silnik jeszcze nie wykonał żadnego cyklu. Uruchom: python -m src.engine.runner';
  else if (!cycle.finished_at) text = `Cykl w toku (start ${formatTime(cycle.started_at)})`;
  else
    text = `Ostatni cykl ${formatTime(cycle.started_at)} · pobrano ${ingest?.fetched ?? 0} · nowych ${ingest?.inserted ?? 0} · duplikatów ${ingest?.duplicates ?? 0}`;

  const failing = status?.failing_sources ?? [];
  // Błędy ostatniego cyklu, których nie ma już na liście źródeł (np. awaria cyklu lub całego źródła).
  const failingKeys = new Set(failing.map(f => f.key));
  const cycleErrors = Object.entries(cycle?.errors ?? {}).filter(([key]) => !failingKeys.has(key));
  const hasErrors = failing.length > 0 || cycleErrors.length > 0;

  return (
    <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg-inset)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            flexShrink: 0,
            background: error || stale || hasErrors ? 'var(--neg)' : 'var(--pos)',
          }}
        />
        <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>{text}</span>
      </div>
      {hasErrors && (
        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {cycleErrors.map(([key, message]) => (
            <div key={`cycle-${key}`} style={errorLine}>
              {key} · {message}
            </div>
          ))}
          {failing.map(f => (
            <div key={f.key} style={errorLine}>
              {f.key} · {f.consecutive_failures}× · {f.last_error}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
