'use client';

import React from 'react';
import { TONE_COLOR, barFill, compareTone, fmtMetric } from '@/lib/analysisFormat';
import type { CompanyMetric } from '@/lib/types';
import s from './analysis.module.css';

function CompareBar({
  metric,
  refValue,
  refLabel,
  currency,
  loading = false,
}: {
  metric: CompanyMetric;
  refValue: number | null | undefined;
  refLabel: string;
  currency: string;
  loading?: boolean;
}) {
  if (loading) return <div className={s.skeleton} style={{ height: 7 }} />;
  const ref = refValue ?? null;
  const tone = compareTone(metric, metric.value, ref);
  const fill = barFill(metric.value, ref);
  const diff =
    metric.value != null && ref != null && ref !== 0 ? ((metric.value - ref) / Math.abs(ref)) * 100 : null;
  const title =
    ref == null
      ? `${refLabel}: brak danych`
      : `${refLabel}: ${fmtMetric(ref, metric.fmt, currency)}` +
        (diff != null ? ` · obecnie ${diff >= 0 ? 'wyżej' : 'niżej'} o ${Math.abs(diff).toFixed(0)}%` : '');
  return (
    <div className={s.bar} title={title} aria-label={title} role="img">
      {tone !== 'none' && (
        <div style={{ position: 'absolute', inset: 0, width: `${fill * 100}%`, background: TONE_COLOR[tone], borderRadius: 2 }} />
      )}
      <div className={s.barMid} />
    </div>
  );
}

/* Tabela wskaźników jednej grupy: wartość TTM + porównanie ze średnią 5Y i medianą peers. */
export default function MetricCard({
  title,
  metrics,
  peerMedians,
  peersLoading,
  hasPeers,
  currency,
}: {
  title: string;
  metrics: CompanyMetric[];
  peerMedians: Record<string, number | null> | null;
  peersLoading: boolean;
  hasPeers: boolean;
  currency: string;
}) {
  return (
    <section className={s.cardPad} aria-label={title}>
      <h3 style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 12 }}>{title}</h3>
      <table className={s.metricTable}>
        <thead>
          <tr>
            <th>Wskaźnik</th>
            <th style={{ textAlign: 'right' }}>Teraz</th>
            <th style={{ width: '22%' }}>vs 5Y</th>
            <th style={{ width: '22%' }}>vs peers</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map(m => (
            <tr key={m.key}>
              <td className={s.metricLabel} title={m.label}>
                {m.label}
              </td>
              <td className={`${s.metricValue} ${s.num}`}>{fmtMetric(m.value, m.fmt, currency)}</td>
              <td>
                <CompareBar metric={m} refValue={m.avg_5y} refLabel="Średnia 5Y" currency={currency} />
              </td>
              <td>
                {hasPeers ? (
                  <CompareBar
                    metric={m}
                    refValue={peerMedians?.[m.key]}
                    refLabel="Mediana peers"
                    currency={currency}
                    loading={peersLoading}
                  />
                ) : (
                  <span style={{ fontSize: 10.5, color: 'var(--faint)' }}>—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
