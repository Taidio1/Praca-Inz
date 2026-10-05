'use client';

import React, { useMemo, useRef, useState } from 'react';
import type { PortfolioHistoryPoint } from '@/lib/types';
import { MONO, fmtCurrency, fmtSignedCurrency, fmtSignedPct } from '@/lib/format';
import FxNote from '@/components/portfolio/FxNote';
import s from '@/components/portfolio/portfolio.module.css';

export type HistoryRange = 30 | 90 | 365;

export const HISTORY_RANGES: { value: HistoryRange; label: string }[] = [
  { value: 30, label: '30 dni' },
  { value: 90, label: '90 dni' },
  { value: 365, label: '1 rok' },
];

interface PortfolioValueChartProps {
  points: PortfolioHistoryPoint[];
  skippedTickers: string[];
  currency: string; // waluta bazowa: każdy punkt po kursie z danego dnia
  fxDate: string | null;
  fxSources: string[];
  range: HistoryRange;
  onRangeChange: (range: HistoryRange) => void;
  loading: boolean;
  error: string | null;
}

const W = 800;
const H = 260;
const PAD_L = 64;
const PAD_R = 16;
const PAD_T = 16;
const PAD_B = 30;
const INNER_W = W - PAD_L - PAD_R;
const INNER_H = H - PAD_T - PAD_B;

function toLocalDate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export default function PortfolioValueChart({
  points,
  skippedTickers,
  currency,
  fxDate,
  fxSources,
  range,
  onRangeChange,
  loading,
  error,
}: PortfolioValueChartProps) {
  const [cursor, setCursor] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const geometry = useMemo(() => {
    if (points.length < 2) return null;
    const values = points.flatMap(p => [p.value, p.cost]);
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const pad = (rawMax - rawMin) * 0.08 || Math.max(rawMax * 0.05, 1);
    const min = Math.max(rawMin - pad, 0);
    const max = rawMax + pad;
    const span = max - min || 1;

    const x = (i: number) => PAD_L + (i / (points.length - 1)) * INNER_W;
    const y = (v: number) => PAD_T + INNER_H - ((v - min) / span) * INNER_H;

    const path = (get: (p: PortfolioHistoryPoint) => number) =>
      points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(get(p)).toFixed(1)}`).join('');

    const line = path(p => p.value);
    return {
      x,
      y,
      line,
      cost: path(p => p.cost),
      area: `${line}L${x(points.length - 1).toFixed(1)},${PAD_T + INNER_H}L${PAD_L},${PAD_T + INNER_H}Z`,
      ticks: Array.from({ length: 5 }, (_, i) => min + (span * i) / 4),
    };
  }, [points]);

  const switcher = (
    <div className={s.seg} role="group" aria-label="Zakres wykresu">
      {HISTORY_RANGES.map(r => (
        <button
          key={r.value}
          type="button"
          className={s.segBtn}
          aria-pressed={r.value === range}
          onClick={() => onRangeChange(r.value)}
        >
          {r.label}
        </button>
      ))}
    </div>
  );

  const frame = (body: React.ReactNode, legend?: React.ReactNode) => (
    <section className={s.card}>
      <div className={s.cardHead}>
        <div>
          <div className={s.eyebrow}>Wartość portfela w czasie</div>
          <div className={s.hint}>Dzienna wycena posiadanych pozycji wobec zainwestowanego kapitału</div>
        </div>
        {switcher}
      </div>
      {body}
      {legend}
    </section>
  );

  if (loading) {
    return frame(
      <div className={s.chartWrap}>
        <div className={s.skeleton} style={{ height: 232 }} />
      </div>,
    );
  }

  if (error) {
    return frame(
      <p className={s.hint} style={{ padding: '20px 16px', color: 'var(--neg)', fontStyle: 'normal' }}>
        {error}
      </p>,
    );
  }

  if (!geometry) {
    return frame(
      <p className={s.hint} style={{ padding: '20px 16px' }}>
        Za mało danych, by narysować wykres — potrzebne są co najmniej dwa dni notowań od pierwszego zakupu.
      </p>,
    );
  }

  const { x, y, line, cost, area, ticks } = geometry;
  const last = points[points.length - 1];
  const active = cursor != null ? points[cursor] : null;
  const xAxisIndices = [
    0,
    Math.floor(points.length / 3),
    Math.floor((2 * points.length) / 3),
    points.length - 1,
  ]
    .sort((a, b) => a - b)
    .filter((index, i, all) => all.indexOf(index) === i);

  const pickIndex = (clientX: number) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const px = ((clientX - rect.left) / rect.width) * W;
    const ratio = (px - PAD_L) / INNER_W;
    setCursor(Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1)))));
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const step = e.key === 'ArrowLeft' ? -1 : 1;
    setCursor(prev => {
      const base = prev ?? points.length - 1;
      return Math.max(0, Math.min(points.length - 1, base + step));
    });
  };

  const tooltipRight = active != null && cursor != null && x(cursor) > W * 0.62;
  const diff = active ? active.value - active.cost : 0;

  return frame(
    <div className={s.chartWrap}>
      <svg
        ref={svgRef}
        className={s.chartSvg}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        tabIndex={0}
        aria-label={`Wartość portfela od ${toLocalDate(points[0].point_date).toLocaleDateString('pl-PL')} do ${toLocalDate(last.point_date).toLocaleDateString('pl-PL')}: od ${fmtCurrency(points[0].value, currency)} do ${fmtCurrency(last.value, currency)}, przy zainwestowanym kapitale ${fmtCurrency(last.cost, currency)}. Strzałki w lewo i prawo odczytują kolejne dni.`}
        onMouseMove={e => pickIndex(e.clientX)}
        onMouseLeave={() => setCursor(null)}
        onTouchStart={e => pickIndex(e.touches[0].clientX)}
        onTouchMove={e => pickIndex(e.touches[0].clientX)}
        onKeyDown={onKeyDown}
        onBlur={() => setCursor(null)}
      >
        <defs>
          <linearGradient id="portfolio-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--area-top)" />
            <stop offset="100%" stopColor="var(--area-bottom)" />
          </linearGradient>
        </defs>

        {ticks.map(tick => (
          <g key={tick}>
            <line
              x1={PAD_L}
              y1={y(tick).toFixed(1)}
              x2={W - PAD_R}
              y2={y(tick).toFixed(1)}
              stroke="var(--chart-grid)"
              strokeWidth="1"
            />
            <text
              x={PAD_L - 10}
              y={y(tick) + 3.5}
              textAnchor="end"
              fontSize="9.5"
              style={{ fill: 'var(--chart-axis)', fontFamily: MONO }}
            >
              {fmtCurrency(tick, currency)}
            </text>
          </g>
        ))}

        {xAxisIndices.map((i, k) => (
          <text
            key={`x-${i}`}
            x={x(i).toFixed(1)}
            y={H - 9}
            textAnchor={k === 0 ? 'start' : k === xAxisIndices.length - 1 ? 'end' : 'middle'}
            fontSize="9.5"
            style={{ fill: 'var(--chart-axis)', fontFamily: MONO }}
          >
            {toLocalDate(points[i].point_date).toLocaleDateString('pl-PL', {
              day: '2-digit',
              month: 'short',
            })}
          </text>
        ))}

        <path d={area} fill="url(#portfolio-area)" />
        <path
          d={cost}
          fill="none"
          stroke="var(--marker)"
          strokeWidth="1.6"
          strokeDasharray="5,4"
          opacity="0.85"
        />
        <path
          d={line}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2.1"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle
          cx={x(points.length - 1).toFixed(1)}
          cy={y(last.value).toFixed(1)}
          r="4"
          fill="var(--accent)"
          stroke="var(--chart-dot-bg)"
          strokeWidth="2"
        />

        {active && cursor != null && (
          <g>
            <line
              x1={x(cursor).toFixed(1)}
              x2={x(cursor).toFixed(1)}
              y1={PAD_T}
              y2={PAD_T + INNER_H}
              stroke="var(--border-3)"
              strokeWidth="1"
            />
            <circle
              cx={x(cursor).toFixed(1)}
              cy={y(active.value).toFixed(1)}
              r="4.5"
              fill="var(--accent)"
              stroke="var(--chart-dot-bg)"
              strokeWidth="2"
            />
          </g>
        )}
      </svg>

      {active && cursor != null && (
        <div
          className={s.tooltip}
          role="status"
          style={{
            left: `${(x(cursor) / W) * 100}%`,
            top: `${(y(active.value) / H) * 100}%`,
            transform: tooltipRight ? 'translate(calc(-100% - 14px), -50%)' : 'translate(14px, -50%)',
          }}
        >
          <div className={s.tooltipDate}>
            {toLocalDate(active.point_date).toLocaleDateString('pl-PL', {
              day: '2-digit',
              month: 'long',
              year: 'numeric',
            })}
          </div>
          <div className="mono num">
            <b>{fmtCurrency(active.value, currency)}</b>
          </div>
          <div className="mono num" style={{ color: 'var(--muted)' }}>
            koszt {fmtCurrency(active.cost, currency)}
          </div>
          <div className="mono num" style={{ color: diff >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
            {fmtSignedCurrency(diff, currency)}
            {active.cost > 0 && ` (${fmtSignedPct((diff / active.cost) * 100, 1)})`}
          </div>
        </div>
      )}
    </div>,
    <div className={s.legend}>
      <span className={s.legendItem}>
        <i className={s.swatch} style={{ background: 'var(--accent)' }} /> Wartość rynkowa
      </span>
      <span className={s.legendItem}>
        <i className={s.swatchDashed} /> Kapitał zainwestowany
      </span>
      {skippedTickers.length > 0 && (
        <span className={s.legendItem} style={{ color: 'var(--marker)' }}>
          Pominięto (brak notowań lub kursu): {skippedTickers.join(', ')}
        </span>
      )}
      <FxNote date={fxDate} sources={fxSources} style={{ marginLeft: 'auto', alignSelf: 'center' }} />
    </div>,
  );
}
