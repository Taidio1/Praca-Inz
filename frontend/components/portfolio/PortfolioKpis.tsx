'use client';

import React from 'react';
import type { PortfolioMetrics } from '@/lib/portfolio';
import { fmtCurrency, fmtSignedCurrency, fmtSignedPct, sentColor, sentLabel } from '@/lib/format';
import FxNote from './FxNote';
import s from './portfolio.module.css';

function tagClass(v: number | null | undefined): string {
  if (v == null || v === 0) return s.tagFlat;
  return v > 0 ? s.tagUp : s.tagDown;
}

function valueColor(v: number | null | undefined): string {
  if (v == null || v === 0) return 'var(--fg-2)';
  return v > 0 ? 'var(--pos)' : 'var(--neg)';
}

export function SentimentBar({ score }: { score: number }) {
  const width = Math.min(Math.abs(score), 1) * 50;
  const left = score < 0 ? 50 - width : 50;
  return (
    <span className={s.sentBar} aria-hidden="true">
      <i style={{ left: `${left}%`, width: `${width}%`, background: sentColor(score) }} />
    </span>
  );
}

export default function PortfolioKpis({ metrics }: { metrics: PortfolioMetrics }) {
  const {
    baseCurrency: base,
    totalValue,
    totalCost,
    totalPl,
    totalPlPct,
    totalPlPrice,
    totalPlFx,
    dayPl,
    dayPct,
    weightedSentiment,
    topWeight,
  } = metrics;

  return (
    <section className={s.kpis} aria-label="Kluczowe wskaźniki portfela">
      <div className={s.kpiHero}>
        <span className={s.kpiLabel}>Wartość portfela</span>
        <span className={`${s.kpiValue} mono num`}>{fmtCurrency(totalValue, base)}</span>
        <span className={s.kpiSub}>
          {dayPl != null ? (
            <>
              <span className={`${tagClass(dayPl)} mono num`}>{fmtSignedPct(dayPct)}</span>
              <span className="mono num" style={{ color: valueColor(dayPl) }}>
                {fmtSignedCurrency(dayPl, base)}
              </span>
              <span style={{ color: 'var(--faint)' }}>za 24h</span>
            </>
          ) : (
            <span style={{ color: 'var(--faint)' }}>brak zmiany 24h w snapshocie</span>
          )}
        </span>
        {metrics.fx && <FxNote date={metrics.fx.date} sources={metrics.fx.sources} style={{ marginTop: 6 }} />}
      </div>

      <div className={s.kpi}>
        <span className={s.kpiLabel}>Kapitał zainwestowany</span>
        <span className={`${s.kpiValue} mono num`} style={{ color: 'var(--fg-2)' }}>
          {totalCost > 0 ? fmtCurrency(totalCost, base) : '—'}
        </span>
        <span className={s.kpiSub}>
          {metrics.priced.length} z {metrics.rows.length} pozycji wycenionych
        </span>
      </div>

      <div className={s.kpi}>
        <span className={s.kpiLabel}>Wynik niezrealizowany</span>
        <span className={`${s.kpiValue} mono num`} style={{ color: valueColor(totalPl) }}>
          {fmtSignedCurrency(totalPl, base)}
        </span>
        <span className={s.kpiSub}>
          {totalPlPct != null ? (
            <span className={`${tagClass(totalPl)} mono num`}>{fmtSignedPct(totalPlPct)}</span>
          ) : (
            <span style={{ color: 'var(--faint)' }}>brak ceny nabycia</span>
          )}
        </span>
        {metrics.fx && totalPlPrice != null && totalPlFx != null && (
          <span
            className={`${s.kpiSub} mono num`}
            style={{ color: 'var(--faint)', fontSize: 11 }}
            title="Wynik w walucie bazowej = zmiana ceny (po kursach z dni zakupu) + zmiana kursu walut"
          >
            cena {fmtSignedCurrency(totalPlPrice, base)} · kurs {fmtSignedCurrency(totalPlFx, base)}
          </span>
        )}
      </div>

      <div className={s.kpi}>
        <span className={s.kpiLabel}>Sentyment portfela</span>
        <span className={`${s.kpiValue} mono num`} style={{ color: weightedSentiment != null ? sentColor(weightedSentiment) : 'var(--faint)' }}>
          {weightedSentiment != null
            ? (weightedSentiment < 0 ? '−' : '+') + Math.abs(weightedSentiment).toFixed(2)
            : '—'}
        </span>
        <span className={s.kpiSub}>
          {weightedSentiment != null ? (
            <>
              <SentimentBar score={weightedSentiment} />
              <span style={{ color: 'var(--faint)' }}>{sentLabel(weightedSentiment).toLowerCase()}, ważony wartością</span>
            </>
          ) : (
            <span style={{ color: 'var(--faint)' }}>brak analizy LLM</span>
          )}
        </span>
      </div>

      <div className={s.kpi}>
        <span className={s.kpiLabel}>Koncentracja</span>
        <span className={`${s.kpiValue} mono num`} style={{ color: 'var(--fg-2)' }}>
          {topWeight?.weight != null ? `${topWeight.weight.toFixed(0)}%` : '—'}
        </span>
        <span className={s.kpiSub}>
          {topWeight ? (
            <>
              największa pozycja:{' '}
              <b className="mono" style={{ color: 'var(--fg-3)' }}>
                {topWeight.position.asset.ticker}
              </b>
            </>
          ) : (
            <span style={{ color: 'var(--faint)' }}>brak wycenionych pozycji</span>
          )}
        </span>
      </div>
    </section>
  );
}
