'use client';

import React from 'react';
import { fmtBig, fmtDatePl, fmtMoney, fmtSignedPctPl } from '@/lib/analysisFormat';
import type { CompanyOverview } from '@/lib/types';
import s from './analysis.module.css';

const HOUR: Record<string, string> = { bmo: 'przed sesją', amc: 'po sesji' };

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className={s.kpiTile} title={hint}>
      <div className={s.kpiTileLabel}>{label}</div>
      <div className={`${s.kpiTileValue} ${s.num}`}>{value}</div>
    </div>
  );
}

/* Kalendarz wyników: termin i konsensus następnego raportu + ostatnie kwartały (EPS vs konsensus). */
export default function EarningsPanel({ data }: { data: CompanyOverview }) {
  const next = data.next_earnings;
  const rows = data.earnings_history;
  const cur = data.currency;

  return (
    <section className={s.cardPad} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <h3 style={{ fontSize: 13.5, fontWeight: 700 }}>Kalendarz wyników</h3>

      <div className={s.kpiGrid3}>
        <Kpi
          label="Następny raport"
          value={next ? fmtDatePl(next.d) : '—'}
          hint={next ? [next.fiscal_quarter, HOUR[next.hour ?? '']].filter(Boolean).join(' · ') : undefined}
        />
        <Kpi label="Prognozowany zysk na akcję" value={fmtMoney(next?.eps_estimate, cur)} hint="Konsensus analityków (Finnhub)" />
        <Kpi label="Prognozowane przychody" value={fmtBig(next?.revenue_estimate, cur)} hint="Konsensus analityków (Finnhub)" />
      </div>

      {rows.length === 0 ? (
        <p className={s.hint} style={{ fontStyle: 'normal' }}>
          Brak historii wyników kwartalnych (wymaga klucza Finnhub).
        </p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className={s.earnTable}>
            <thead>
              <tr>
                <th>Kwartał</th>
                <th>EPS rzecz. / prog.</th>
                <th>Przychody</th>
                <th style={{ textAlign: 'right' }}>Zaskoczenie EPS</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const sp = r.surprise_pct;
                const tone = sp == null ? 'var(--muted)' : sp > 0 ? 'var(--pos)' : sp < 0 ? 'var(--neg)' : 'var(--muted)';
                const label = sp == null ? '—' : sp > 0 ? 'Pozytywne' : sp < 0 ? 'Negatywne' : 'Zgodne';
                return (
                  <tr key={r.period}>
                    <td>
                      <div style={{ fontWeight: 700 }}>{r.fiscal_quarter ?? '—'}</div>
                      <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>okres do {fmtDatePl(r.period)}</div>
                    </td>
                    <td className={s.num}>
                      <b>{fmtMoney(r.eps_actual, cur)}</b>
                      <span style={{ color: 'var(--muted)' }}> / {fmtMoney(r.eps_estimate, cur)}</span>
                    </td>
                    <td className={s.num}>{fmtBig(r.revenue_actual, cur)}</td>
                    <td className={s.num} style={{ textAlign: 'right', color: tone, fontWeight: 700, whiteSpace: 'nowrap' }}>
                      {label} {sp != null ? fmtSignedPctPl(sp, 1) : ''}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className={s.hint}>
        EPS rzeczywisty i konsensus: Finnhub (EPS raportowany przez spółkę, często skorygowany). Przychody kwartału: raporty
        SEC (10-Q/10-K). Prognozy przychodów dla minionych kwartałów nie są dostępne w darmowym planie. Prognozy analityków
        mają charakter informacyjny.
      </p>
    </section>
  );
}
