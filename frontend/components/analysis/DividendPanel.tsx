'use client';

import React, { useMemo, useState } from 'react';
import { fmtDatePl, fmtMoney, fmtNum, fmtSignedPctPl } from '@/lib/analysisFormat';
import { plural } from '@/lib/format';
import type { CompanyDividends } from '@/lib/types';
import { niceTicks } from './PriceHistoryChart';
import { useWidth } from './useWidth';
import s from './analysis.module.css';

type Span = 3 | 5 | 10 | 'MAX';
const SPANS: Span[] = [3, 5, 10, 'MAX'];
const CHART_H = 200;
const PAD = { top: 12, right: 46, bottom: 22, left: 52 };

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className={s.kpiTile} title={hint}>
      <div className={s.kpiTileLabel}>{label}</div>
      <div className={`${s.kpiTileValue} ${s.num}`}>{value}</div>
    </div>
  );
}

/* Słupki: dywidenda roczna na akcję (bieżący rok obrysem). Linia: stopa dywidendy na koniec roku. */
function DividendChart({ years, currency }: { years: CompanyDividends['years']; currency: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const content = (() => {
    if (width === 0 || years.length === 0) return null;
    const innerW = width - PAD.left - PAD.right;
    const innerH = CHART_H - PAD.top - PAD.bottom;
    const maxDps = Math.max(...years.map(y => y.dps)) * 1.12 || 1;
    const yields = years.map(y => y.yield_pct).filter((v): v is number => v != null);
    const maxYield = (yields.length ? Math.max(...yields) : 1) * 1.25 || 1;
    const slot = innerW / years.length;
    const barW = Math.max(3, Math.min(34, slot * 0.6));
    const xc = (i: number) => PAD.left + slot * i + slot / 2;
    const yD = (v: number) => PAD.top + innerH - (v / maxDps) * innerH;
    const yY = (v: number) => PAD.top + innerH - (v / maxYield) * innerH;
    const linePts = years
      .map((y, i) => (y.yield_pct != null ? `${xc(i).toFixed(1)},${yY(y.yield_pct).toFixed(1)}` : null))
      .filter(Boolean);
    const labelEvery = Math.ceil(years.length / 14);
    const hv = hover != null ? years[hover] : null;

    return (
      <>
        <svg width={width} height={CHART_H} role="img" aria-label="Historia dywidendy na akcję i stopy dywidendy">
          {niceTicks(0, maxDps, 4).map(v => (
            <g key={`d${v}`}>
              <line x1={PAD.left} x2={PAD.left + innerW} y1={yD(v)} y2={yD(v)} stroke="var(--chart-grid)" strokeDasharray="3 4" />
              <text x={PAD.left - 6} y={yD(v) + 3.5} fontSize="10" fill="var(--chart-axis)" textAnchor="end">
                {fmtNum(v, v === 0 ? 0 : 2)}
              </text>
            </g>
          ))}
          {yields.length > 0 &&
            niceTicks(0, maxYield, 4).map(v => (
              <text key={`y${v}`} x={PAD.left + innerW + 6} y={yY(v) + 3.5} fontSize="10" fill="var(--marker)">
                {fmtNum(v, 1)}%
              </text>
            ))}
          {years.map((y, i) => (
            <rect
              key={y.year}
              x={xc(i) - barW / 2}
              y={yD(y.dps)}
              width={barW}
              height={Math.max(1, PAD.top + innerH - yD(y.dps))}
              rx={2}
              fill={y.partial ? 'transparent' : 'var(--pos)'}
              stroke={y.partial ? 'var(--pos)' : 'none'}
              strokeWidth={1.5}
              opacity={hover == null || hover === i ? 1 : 0.55}
            />
          ))}
          {linePts.length > 1 && <polyline points={linePts.join(' ')} fill="none" stroke="var(--marker)" strokeWidth={1.6} />}
          {years.map((y, i) =>
            y.yield_pct != null && years.length <= 25 ? (
              <circle key={`c${y.year}`} cx={xc(i)} cy={yY(y.yield_pct)} r={3.4} fill="var(--marker)" stroke="var(--chart-dot-bg)" strokeWidth={1.2} />
            ) : null,
          )}
          {years.map((y, i) =>
            i % labelEvery === 0 || i === years.length - 1 ? (
              <text key={`x${y.year}`} x={xc(i)} y={CHART_H - 5} fontSize="10" fill="var(--chart-axis)" textAnchor="middle">
                {`'${String(y.year).slice(2)}`}
              </text>
            ) : null,
          )}
          {years.map((y, i) => (
            <rect
              key={`h${y.year}`}
              x={PAD.left + slot * i}
              y={PAD.top}
              width={slot}
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>
        <div style={{ minHeight: 18, fontSize: 11.5, color: 'var(--fg-3)' }}>
          {hv ? (
            <>
              <b>{hv.year}</b>
              {hv.partial ? ' (rok w toku)' : ''}: dywidenda {fmtMoney(hv.dps, currency)}
              {hv.yield_pct != null ? ` · stopa ${fmtNum(hv.yield_pct, 2)}% (cena z końca roku)` : ''}
            </>
          ) : (
            <span className={s.hint}>Najedź na słupek, by zobaczyć szczegóły roku.</span>
          )}
        </div>
      </>
    );
  })();

  return (
    <div ref={ref} style={{ minHeight: CHART_H + 18 }}>
      {content}
    </div>
  );
}

export default function DividendPanel({ dividends, currency }: { dividends: CompanyDividends | null; currency: string }) {
  const [span, setSpan] = useState<Span>(10);
  const years = useMemo(() => {
    const all = dividends?.years ?? [];
    if (span === 'MAX') return all;
    const cutoff = new Date().getFullYear() - span;
    return all.filter(y => y.year > cutoff);
  }, [dividends, span]);

  if (!dividends) {
    return (
      <section className={s.cardPad}>
        <h3 style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 8 }}>Historia dywidendy</h3>
        <p className={s.hint} style={{ fontStyle: 'normal' }}>
          Spółka nie wypłaca dywidendy (brak wypłat w ostatnich 2 latach w historii notowań).
        </p>
      </section>
    );
  }

  const d = dividends;
  const lastFull = new Date().getFullYear() - 1;
  // Seria sięga początku dostępnej historii → to dolne ograniczenie, nie pełna długość.
  const payingCapped = lastFull - d.paying_streak + 1 <= d.history_from;

  return (
    <section className={s.cardPad} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ fontSize: 13.5, fontWeight: 700 }}>Historia dywidendy</h3>
        <div className={s.seg} role="group" aria-label="Zakres lat">
          {SPANS.map(sp => (
            <button key={sp} type="button" className={sp === span ? s.segBtnOn : s.segBtn} onClick={() => setSpan(sp)}>
              {sp === 'MAX' ? 'MAX' : `${sp}Y`}
            </button>
          ))}
        </div>
      </div>

      <div className={s.kpiGrid}>
        <Kpi label="Stopa dywidendy" value={d.yield_ttm != null ? `${fmtNum(d.yield_ttm, 2)}%` : '—'} hint="Dywidendy z ostatnich 12 mies. / bieżąca cena" />
        <Kpi
          label="Dywidenda na akcję"
          value={fmtMoney(d.dps_ttm, currency)}
          hint={`Suma wypłat z ostatnich 12 mies. (wg dat odcięcia).${d.indicated_annual != null ? ` Wg bieżącej stawki: ${fmtMoney(d.indicated_annual, currency)} rocznie.` : ''}`}
        />
        <Kpi label="Wskaźnik wypłaty" value={d.payout_ratio != null ? `${fmtNum(d.payout_ratio, 1)}%` : '—'} hint="Dywidendy wypłacone (SEC, TTM) / zysk netto TTM" />
        <Kpi label="Pokrycie dywidendy FCF" value={d.fcf_coverage != null ? `${fmtNum(d.fcf_coverage, 1)}×` : '—'} hint="Wolne przepływy pieniężne TTM / dywidendy wypłacone TTM" />
      </div>

      <div className={s.badges}>
        <span
          className={d.growth_streak > 0 ? s.badge : s.badgeMuted}
          title="Kolejne lata kalendarzowe, w których stawka dywidendy na koniec roku była wyższa niż rok wcześniej. Spółki często liczą serie wg lat obrotowych — wynik może się różnić."
        >
          Wzrost dywidendy: {d.growth_streak} {plural(d.growth_streak, 'rok', 'lata', 'lat')}
        </span>
        <span className={s.badge} title={`Dostępna historia wypłat od ${d.history_from} r.`}>
          {payingCapped ? 'Min. ' : ''}
          {d.paying_streak} {plural(d.paying_streak, 'rok', 'lata', 'lat')} wypłat
        </span>
        {(['3', '5', '10'] as const).map(k =>
          d.cagr[k] != null ? (
            <span key={k} className={(d.cagr[k] ?? 0) >= 0 ? s.badge : s.badgeMuted} title={`Średnioroczne tempo wzrostu rocznej dywidendy na akcję, ${k} lat do ${lastFull} r.`}>
              CAGR {k}L {fmtSignedPctPl(d.cagr[k], 1)}
            </span>
          ) : null,
        )}
      </div>

      <DividendChart years={years} currency={currency} />

      <div className={s.detailRows}>
        <div className={s.detailRow}>
          <span>Ostatnia wypłata</span>
          <span className={s.num}>{fmtMoney(d.last_amount, currency)}</span>
        </div>
        <div className={s.detailRow}>
          <span>Częstotliwość</span>
          <span>{d.frequency ?? '—'}</span>
        </div>
        <div className={s.detailRow}>
          <span>Dzień odcięcia prawa</span>
          <span>{fmtDatePl(d.last_ex_date)}</span>
        </div>
        <div className={s.detailRow}>
          <span>Dywidenda wg bieżącej stawki</span>
          <span className={s.num}>{d.indicated_annual != null ? `${fmtMoney(d.indicated_annual, currency)} / rok` : '—'}</span>
        </div>
      </div>
      <p className={s.hint}>
        Kwoty skorygowane o splity (Yahoo Finance), lata kalendarzowe wg dat odcięcia. Daty deklaracji i wypłaty nie są
        dostępne w darmowych źródłach danych.
      </p>
    </section>
  );
}
