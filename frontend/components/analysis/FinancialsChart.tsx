'use client';

import React, { useMemo, useState } from 'react';
import { fmtBig, fmtNum, fmtSignedPctPl } from '@/lib/analysisFormat';
import type { CompanyFinancialYear } from '@/lib/types';
import s from './analysis.module.css';

type SeriesKey = 'revenue' | 'gross_profit' | 'operating_income' | 'net_income' | 'ocf' | 'fcf';
type Span = 3 | 5 | 10 | 'MAX';

const SERIES: { key: SeriesKey; label: string }[] = [
  { key: 'revenue', label: 'Przychody' },
  { key: 'gross_profit', label: 'Zysk brutto' },
  { key: 'operating_income', label: 'Zysk operacyjny' },
  { key: 'net_income', label: 'Zysk netto' },
  { key: 'ocf', label: 'Przepływy operacyjne' },
  { key: 'fcf', label: 'Wolne przepływy (FCF)' },
];

const SPANS: Span[] = [3, 5, 10, 'MAX'];

function scaleOf(max: number): [number, string] {
  if (max >= 1e12) return [1e12, 'bln'];
  if (max >= 1e9) return [1e9, 'mld'];
  if (max >= 1e6) return [1e6, 'mln'];
  return [1, ''];
}

/* Roczne wartości z raportów 10-K: wybór pozycji, zakres lat, pobranie CSV. */
export default function FinancialsChart({
  financials,
  ticker,
  currency,
}: {
  financials: CompanyFinancialYear[];
  ticker: string;
  currency: string;
}) {
  const [key, setKey] = useState<SeriesKey>('revenue');
  const [span, setSpan] = useState<Span>(10);
  const [hover, setHover] = useState<number | null>(null);

  const rows = useMemo(() => {
    const withValue = financials.filter(f => f[key] != null);
    return span === 'MAX' ? withValue : withValue.slice(-span);
  }, [financials, key, span]);

  const values = rows.map(r => r[key] as number);
  const maxAbs = Math.max(1, ...values.map(Math.abs));
  const hasNeg = values.some(v => v < 0);
  const [div, unit] = scaleOf(maxAbs);
  const first = values[0];
  const last = values[values.length - 1];
  const years = rows.length > 1 ? rows[rows.length - 1].fiscal_year - rows[0].fiscal_year : 0;
  const cagr = years > 0 && first > 0 && last > 0 ? ((last / first) ** (1 / years) - 1) * 100 : null;

  const download = () => {
    const header = ['rok_obrotowy', 'koniec_okresu', ...SERIES.map(x => x.key)].join(',');
    const lines = financials.map(f =>
      [f.fiscal_year, f.period_end, ...SERIES.map(x => (f[x.key] ?? '').toString())].join(','),
    );
    const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${ticker}_dane_roczne_sec.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const label = SERIES.find(x => x.key === key)?.label ?? '';
  const CHART_H = 210;
  const zeroY = hasNeg ? CHART_H / 2 : CHART_H;
  const unitH = hasNeg ? CHART_H / 2 : CHART_H;

  return (
    <section className={s.cardPad}>
      <div className={s.finHead}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <select className={s.select} value={key} onChange={e => setKey(e.target.value as SeriesKey)} aria-label="Pozycja finansowa">
            {SERIES.map(x => (
              <option key={x.key} value={x.key}>
                {x.label}
              </option>
            ))}
          </select>
          {cagr != null && (
            <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>
              CAGR {rows[0].fiscal_year}–{rows[rows.length - 1].fiscal_year}:{' '}
              <b style={{ color: cagr >= 0 ? 'var(--pos)' : 'var(--neg)' }}>{fmtSignedPctPl(cagr)}</b>
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div className={s.seg} role="group" aria-label="Zakres lat">
            {SPANS.map(sp => (
              <button key={sp} type="button" className={sp === span ? s.segBtnOn : s.segBtn} onClick={() => setSpan(sp)}>
                {sp === 'MAX' ? 'MAX' : `${sp}Y`}
              </button>
            ))}
          </div>
          <button type="button" className={s.ghostBtn} onClick={download} disabled={financials.length === 0}>
            Pobierz CSV
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div style={{ padding: '30px 0', fontSize: 12, color: 'var(--muted-2)', fontStyle: 'italic' }}>
          Spółka nie raportuje pozycji „{label}” w formacie US-GAAP.
        </div>
      ) : (
        <div style={{ position: 'relative' }}>
          <div style={{ fontSize: 10, color: 'var(--muted-2)', marginBottom: 6 }}>
            {unit ? `${unit} ${currency}` : currency}
          </div>
          <div style={{ display: 'flex', alignItems: 'stretch', gap: 6, height: CHART_H, borderBottom: hasNeg ? 'none' : '1px solid var(--chart-zero)', position: 'relative' }}>
            {hasNeg && <div style={{ position: 'absolute', left: 0, right: 0, top: zeroY, height: 1, background: 'var(--chart-zero)' }} />}
            {rows.map((r, i) => {
              const v = r[key] as number;
              const h = (Math.abs(v) / maxAbs) * (unitH - 18);
              return (
                <div
                  key={r.fiscal_year}
                  style={{ flex: 1, position: 'relative', minWidth: 0 }}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                >
                  <div
                    style={{
                      position: 'absolute',
                      left: '14%',
                      right: '14%',
                      top: v >= 0 ? zeroY - h : zeroY,
                      height: Math.max(h, 1),
                      background: v >= 0 ? 'var(--accent)' : 'var(--neg)',
                      opacity: hover == null || hover === i ? 1 : 0.55,
                      borderRadius: v >= 0 ? '4px 4px 0 0' : '0 0 4px 4px',
                      transition: 'opacity .15s',
                    }}
                  />
                  {(hover === i || rows.length <= 10) && (
                    <div
                      className="num"
                      style={{
                        position: 'absolute',
                        left: 0,
                        right: 0,
                        textAlign: 'center',
                        top: v >= 0 ? zeroY - h - 15 : zeroY + h + 2,
                        fontSize: 9.5,
                        color: hover === i ? 'var(--fg)' : 'var(--muted)',
                        fontWeight: hover === i ? 700 : 500,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {fmtNum(v / div, maxAbs / div >= 100 ? 0 : 1)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            {rows.map(r => (
              <div key={r.fiscal_year} style={{ flex: 1, textAlign: 'center', fontSize: 10, color: 'var(--chart-axis)', minWidth: 0 }}>
                {rows.length > 16 ? `'${String(r.fiscal_year).slice(2)}` : `FY${r.fiscal_year}`}
              </div>
            ))}
          </div>
          {hover != null && rows[hover] && (
            <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--fg-3)' }}>
              FY{rows[hover].fiscal_year} (do {rows[hover].period_end}): <b>{fmtBig(rows[hover][key], currency)}</b>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
