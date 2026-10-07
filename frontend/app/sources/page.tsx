'use client';

import React, { useEffect, useState } from 'react';
import * as api from '@/lib/api';
import type { EvaluationMetrics, Insight, Trace } from '@/lib/types';
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

const sectionStyle: React.CSSProperties = {
  background: 'var(--panel)',
  border: '1px solid var(--border)',
  borderRadius: 12,
  margin: '10px 12px 0',
  overflow: 'hidden',
};

const sectionHeading: React.CSSProperties = {
  padding: '11px 14px 8px',
  borderBottom: '1px solid var(--border)',
  fontSize: 13,
  fontWeight: 650,
  color: 'var(--fg-2)',
};

export default function SourcesPage() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const [traceOpen, setTraceOpen] = useState(false);
  const [expandedTrace, setExpandedTrace] = useState<string | null>(null);
  const [traces, setTraces] = useState<Record<string, Trace | 'loading' | 'error'>>({});
  const [evaluation, setEvaluation] = useState<EvaluationMetrics | null>(null);

  const loadEvaluation = () => {
    api.getEvaluationMetrics().then(setEvaluation).catch(() => setEvaluation(null));
  };

  useEffect(() => {
    loadEvaluation();
  }, []);

  /* Insighty do sekcji śladu LLM — trace dociągany przy rozwinięciu. */
  useEffect(() => {
    if (!traceOpen) return;
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
  }, [traceOpen]);

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
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ order: 0 }}><EngineStatusBar /></div>

      {/* Metryki jakości filtra: tylko ręcznie oznaczone pary news–aktywo. */}
      <div style={{ ...sectionStyle, order: 2, padding: '14px 14px 12px' }}>
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
            {evaluation ? `${evaluation.labeled_pairs} oznaczonych` : 'materiał ewaluacyjny'}
          </span>
        </div>
        {!evaluation || evaluation.labeled_pairs === 0 ? (
          <div style={emptyNote}>Oznacz w audycie pary news–aktywo jako trafne lub nietrafne, aby zbudować zbiór referencyjny i obliczyć metryki.</div>
        ) : (
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
            {([['Precision', evaluation.precision], ['Recall', evaluation.recall], ['F1', evaluation.f1]] as const).map(([label, value]) => (
              <span key={label} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px', fontSize: 11, color: 'var(--fg-3)' }}>
                {label}: <strong style={{ fontFamily: MONO }}>{value == null ? '—' : `${(value * 100).toFixed(1)}%`}</strong>
              </span>
            ))}
            <span style={{ fontSize: 10.5, color: 'var(--faint)', alignSelf: 'center' }}>TP {evaluation.true_positive} · FP {evaluation.false_positive} · FN {evaluation.false_negative} · TN {evaluation.true_negative} · próg {evaluation.threshold.toFixed(2)}</span>
          </div>
        )}
      </div>

      <div style={{ ...sectionStyle, order: 3 }}><FunnelPanel /></div>

      <div style={{ ...sectionStyle, order: 4 }}>
        <div style={sectionHeading}>Audyt źródeł</div>
        <AuditList onLabelSaved={loadEvaluation} />
      </div>

      {/* Ślad analizy LLM */}
      <div style={{ ...sectionStyle, order: 1, padding: '0 14px 12px' }}>
        <button
          type="button"
          onClick={() => setTraceOpen(open => !open)}
          aria-expanded={traceOpen}
          style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 0', border: 'none', background: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
        >
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Ślad analizy LLM — prompt + odpowiedź
          </span>
          <span aria-hidden="true" style={{ color: 'var(--muted-2)', fontSize: 18, transform: traceOpen ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform .18s ease' }}>›</span>
        </button>
        {traceOpen && <>
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
        </>}
      </div>
    </div>
  );
}
