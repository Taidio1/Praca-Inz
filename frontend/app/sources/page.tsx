'use client';

import React, { useEffect, useState } from 'react';
import * as api from '@/lib/api';
import type { Insight, Trace } from '@/lib/types';
import { formatTime, MONO } from '@/lib/format';
import EngineStatusBar from '@/components/sources/EngineStatusBar';
import FunnelPanel from '@/components/sources/FunnelPanel';
import AuditList from '@/components/sources/AuditList';

const emptyNote: React.CSSProperties = {
  fontSize: 11.5,
  color: 'var(--muted-2)',
  fontStyle: 'italic',
  lineHeight: 1.5,
};

export default function SourcesPage() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const [expandedTrace, setExpandedTrace] = useState<string | null>(null);
  const [traces, setTraces] = useState<Record<string, Trace | 'loading' | 'error'>>({});

  /* Insighty do sekcji śladu LLM — trace dociągany przy rozwinięciu. */
  useEffect(() => {
    let cancelled = false;
    api
      .getFeed({ limit: 10 })
      .then(page => {
        if (!cancelled) setInsights(page.items);
      })
      .catch(() => {
        /* sekcja śladu pokaże pusty stan */
      })
      .finally(() => {
        if (!cancelled) setInsightsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleTrace = (insightId: string) => {
    const next = expandedTrace === insightId ? null : insightId;
    setExpandedTrace(next);
    if (next && !traces[next]) {
      setTraces(prev => ({ ...prev, [next]: 'loading' }));
      api
        .getInsightTrace(next)
        .then(tr => setTraces(prev => ({ ...prev, [next]: tr })))
        .catch(() => setTraces(prev => ({ ...prev, [next]: 'error' })));
    }
  };

  return (
    <>
      <EngineStatusBar />

      {/* Metryki jakości filtra — brak endpointu i zbioru ewaluacyjnego */}
      <div style={{ padding: '14px 14px 12px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Jakość filtra trafności
          </div>
          <span
            style={{
              fontSize: 9,
              fontFamily: MONO,
              color: 'var(--faint)',
              background: 'var(--bg-inset)',
              border: '1px solid var(--border)',
              borderRadius: 5,
              padding: '2px 7px',
            }}
          >
            materiał ewaluacyjny
          </span>
        </div>
        <div style={emptyNote}>
          Metryki (precision / recall / F1) będą dostępne po przygotowaniu oznaczonego zbioru ewaluacyjnego i ewaluacji filtra trafności.
        </div>
      </div>

      <FunnelPanel />

      <AuditList />

      {/* Ślad analizy LLM */}
      <div style={{ padding: '6px 14px 16px' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 9 }}>
          Ślad analizy LLM — prompt + odpowiedź
        </div>
        {insightsLoading && <div style={{ fontSize: 12, color: 'var(--muted-2)', padding: '8px 0' }}>Ładowanie…</div>}
        {!insightsLoading && insights.length === 0 && (
          <div style={emptyNote}>Brak zapisanych analiz LLM — ślad pojawi się po pierwszej syntezie wykonanej przez silnik.</div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {insights.map(ins => {
            const expanded = expandedTrace === ins.id;
            const tr = traces[ins.id];
            return (
              <div key={ins.id} style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
                <button
                  type="button"
                  onClick={() => toggleTrace(ins.id)}
                  style={{
                    width: '100%',
                    padding: '11px 13px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontFamily: 'inherit',
                  }}
                >
                  <span
                    style={{
                      fontFamily: MONO,
                      fontSize: 11,
                      fontWeight: 500,
                      padding: '4px 8px',
                      borderRadius: 6,
                      background: 'var(--accent-soft)',
                      color: 'var(--accent)',
                      border: '1px solid var(--accent-line)',
                      flexShrink: 0,
                    }}
                  >
                    {ins.asset_ticker ?? '—'}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {ins.title}
                    </div>
                    <div style={{ fontSize: 9.5, color: 'var(--muted-2)', fontFamily: MONO, marginTop: 2 }}>
                      {typeof tr === 'object'
                        ? `${tr.model} · ${tr.tokens_in} tok in · ${tr.tokens_out} tok out · ${(tr.latency_ms / 1000).toFixed(1)}s · $${tr.cost_usd.toFixed(4)}`
                        : formatTime(ins.created_at)}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: 18,
                      color: 'var(--muted-2)',
                      flexShrink: 0,
                      transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                      transition: 'transform .18s ease',
                    }}
                  >
                    ›
                  </span>
                </button>
                {expanded && (
                  <div style={{ padding: '0 13px 13px' }}>
                    {tr === 'loading' && <div style={{ fontSize: 11.5, color: 'var(--muted-2)' }}>Ładowanie śladu…</div>}
                    {tr === 'error' && (
                      <div style={{ fontSize: 11.5, color: 'var(--neg)' }}>Brak zapisu audytu LLM dla tego insightu.</div>
                    )}
                    {typeof tr === 'object' && (
                      <>
                        <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 5 }}>
                          Prompt → ({tr.provider} · {tr.model})
                        </div>
                        <pre
                          style={{
                            background: 'var(--bg-3)',
                            border: '1px solid var(--border)',
                            borderRadius: 8,
                            padding: '10px 11px',
                            fontFamily: MONO,
                            fontSize: 10.5,
                            lineHeight: 1.55,
                            color: 'var(--fg-4)',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            marginBottom: 11,
                            overflowX: 'auto',
                            maxHeight: 320,
                            overflowY: 'auto',
                          }}
                        >
                          {tr.prompt}
                        </pre>
                        <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 5 }}>
                          ← Odpowiedź
                        </div>
                        <pre
                          style={{
                            background: 'var(--bg-3)',
                            border: '1px solid var(--accent-line)',
                            borderRadius: 8,
                            padding: '10px 11px',
                            fontFamily: MONO,
                            fontSize: 10.5,
                            lineHeight: 1.55,
                            color: 'var(--fg-3)',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            overflowX: 'auto',
                            maxHeight: 320,
                            overflowY: 'auto',
                          }}
                        >
                          {tr.response}
                        </pre>
                        <div style={{ fontSize: 9, color: 'var(--faint)', marginTop: 8, fontStyle: 'italic' }}>
                          Zapisane w bazie (źródło + trafność + prompt + odpowiedź) — pełny ślad audytowy.
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
