'use client';

import React, { useMemo, useState } from 'react';
import { fmtDatePl, fmtNum } from '@/lib/analysisFormat';
import type { CompanyChartEvent } from '@/lib/types';
import { useWidth } from './useWidth';

export type ChartRange = '1M' | '3M' | 'YTD' | '1Y' | '5Y';

interface Props {
  prices: { d: string; close: number }[];
  events: CompanyChartEvent[];
  range: ChartRange;
  showEarnings: boolean;
  showDividends: boolean;
  currency: string;
}

const HEIGHT = 190;
const PAD = { top: 10, right: 62, bottom: 22, left: 4 };

export function rangeStart(range: ChartRange, last: Date): Date {
  const d = new Date(last);
  if (range === 'YTD') return new Date(last.getFullYear(), 0, 1);
  const days = { '1M': 30, '3M': 91, '1Y': 365, '5Y': 1826 }[range];
  d.setDate(d.getDate() - days);
  return d;
}

export function niceTicks(min: number, max: number, count = 3): number[] {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= step0) ?? step0;
  const out: number[] = [];
  // Liczenie od indeksu (nie przez sumowanie) — bez dryfu typu 1e-15 → „−0,00".
  for (let i = Math.ceil(min / step); i * step <= max; i++) out.push(i === 0 ? 0 : i * step);
  return out;
}

/* Linia dziennych zamknięć z markerami publikacji raportów (10-Q/10-K) i dywidend. */
export default function PriceHistoryChart(props: Props) {
  const [wrapRef, width] = useWidth<HTMLDivElement>();
  const { prices, range } = props;

  const series = useMemo(() => {
    if (prices.length === 0) return [];
    const last = new Date(`${prices[prices.length - 1].d}T00:00:00`);
    const from = rangeStart(range, last).toISOString().slice(0, 10);
    return prices.filter(p => p.d >= from);
  }, [prices, range]);

  return (
    <div ref={wrapRef} style={{ position: 'relative', minHeight: HEIGHT }}>
      {width > 0 && series.length >= 2 ? (
        <ChartBody {...props} series={series} width={width} />
      ) : (
        width > 0 && (
          <div style={{ height: HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11.5, color: 'var(--muted-2)', fontStyle: 'italic' }}>
            Brak notowań w tym okresie
          </div>
        )
      )}
    </div>
  );
}

function ChartBody({
  series,
  width,
  events,
  range,
  showEarnings,
  showDividends,
  currency,
}: Props & { series: { d: string; close: number }[]; width: number }) {
  const [hover, setHover] = useState<number | null>(null);

  const innerW = width - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const t0 = new Date(series[0].d).getTime();
  const t1 = new Date(series[series.length - 1].d).getTime();
  const closes = series.map(p => p.close);
  const lo = Math.min(...closes);
  const hi = Math.max(...closes);
  const padY = (hi - lo) * 0.08 || hi * 0.05;
  const yMin = lo - padY;
  const yMax = hi + padY;
  const x = (iso: string) => PAD.left + ((new Date(iso).getTime() - t0) / (t1 - t0 || 1)) * innerW;
  const y = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin)) * innerH;

  const line = series.map((p, i) => `${i ? 'L' : 'M'}${x(p.d).toFixed(1)},${y(p.close).toFixed(1)}`).join('');
  const area = `${line}L${x(series[series.length - 1].d).toFixed(1)},${PAD.top + innerH}L${x(series[0].d).toFixed(1)},${PAD.top + innerH}Z`;
  const up = series[series.length - 1].close >= series[0].close;
  const stroke = up ? 'var(--pos)' : 'var(--neg)';

  const closeOn = (iso: string): number | null => {
    let found: number | null = null;
    for (const p of series) {
      if (p.d > iso) break;
      found = p.close;
    }
    return found;
  };

  const visibleEvents = events.filter(
    e => e.d >= series[0].d && e.d <= series[series.length - 1].d && (e.kind === 'earnings' ? showEarnings : showDividends),
  );

  // Etykiety osi X: lata dla długich zakresów, miesiące dla krótkich.
  const spanDays = (t1 - t0) / 86_400_000;
  const xTicks: { pos: number; label: string }[] = [];
  const start = new Date(t0);
  if (spanDays > 500) {
    for (let yr = start.getFullYear() + 1; yr <= new Date(t1).getFullYear(); yr++) {
      xTicks.push({ pos: x(`${yr}-01-01`), label: String(yr) });
    }
  } else {
    const step = spanDays > 200 ? 2 : 1;
    const d = new Date(start.getFullYear(), start.getMonth() + 1, 1);
    while (d.getTime() <= t1) {
      xTicks.push({ pos: x(d.toISOString().slice(0, 10)), label: d.toLocaleDateString('pl-PL', { month: 'short' }) });
      d.setMonth(d.getMonth() + step);
    }
    if (spanDays < 40) xTicks.splice(0, xTicks.length);
  }

  const hp = hover != null ? series[hover] : null;
  const hoverEvents = hp ? events.filter(e => e.d === hp.d) : [];

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - rect.left) / rect.width;
    const target = t0 + rel * (t1 - t0);
    let best = 0;
    let bestDist = Infinity;
    series.forEach((p, i) => {
      const dist = Math.abs(new Date(p.d).getTime() - target);
      if (dist < bestDist) {
        best = i;
        bestDist = dist;
      }
    });
    setHover(best);
  };

  return (
    <>
      <svg width={width} height={HEIGHT} role="img" aria-label={`Wykres ceny, zakres ${range}`}>
        <defs>
          <linearGradient id="analysisArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={up ? 'var(--pos)' : 'var(--neg)'} stopOpacity="0.22" />
            <stop offset="100%" stopColor={up ? 'var(--pos)' : 'var(--neg)'} stopOpacity="0" />
          </linearGradient>
        </defs>
        {niceTicks(yMin, yMax).map(v => (
          <g key={v}>
            <line x1={PAD.left} x2={PAD.left + innerW} y1={y(v)} y2={y(v)} stroke="var(--chart-grid)" strokeDasharray="3 4" />
            <text x={PAD.left + innerW + 8} y={y(v) + 3.5} fontSize="10" fill="var(--chart-axis)">
              {fmtNum(v, v === 0 || v >= 100 ? 0 : 2)}
            </text>
          </g>
        ))}
        {xTicks.map(t => (
          <text key={t.label + t.pos} x={t.pos} y={HEIGHT - 5} fontSize="10" fill="var(--chart-axis)" textAnchor="middle">
            {t.label}
          </text>
        ))}
        <path d={area} fill="url(#analysisArea)" />
        <path d={line} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinejoin="round" />
        {visibleEvents.map(ev => {
          const c = closeOn(ev.d);
          if (c == null) return null;
          return (
            <circle
              key={`${ev.kind}${ev.d}`}
              cx={x(ev.d)}
              cy={y(c)}
              r={3.6}
              fill={ev.kind === 'earnings' ? 'var(--marker)' : 'var(--accent)'}
              stroke="var(--chart-dot-bg)"
              strokeWidth="1.2"
            />
          );
        })}
        {hp && (
          <g pointerEvents="none">
            <line x1={x(hp.d)} x2={x(hp.d)} y1={PAD.top} y2={PAD.top + innerH} stroke="var(--border-3)" />
            <circle cx={x(hp.d)} cy={y(hp.close)} r={4} fill={stroke} stroke="var(--chart-dot-bg)" strokeWidth="1.5" />
          </g>
        )}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={innerW}
          height={innerH}
          fill="transparent"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        />
      </svg>
      {hp && (
        <div
          style={{
            position: 'absolute',
            top: 4,
            left: Math.min(Math.max(x(hp.d) - 80, 0), width - 170),
            width: 160,
            pointerEvents: 'none',
            background: 'var(--panel-2)',
            border: '1px solid var(--border-2)',
            borderRadius: 8,
            padding: '6px 9px',
            fontSize: 11,
            boxShadow: '0 6px 18px rgba(0,0,0,.25)',
          }}
        >
          <div style={{ color: 'var(--muted)' }}>{fmtDatePl(hp.d)}</div>
          <div style={{ fontWeight: 700, color: 'var(--fg)' }} className="num">
            {fmtNum(hp.close)} {currency}
          </div>
          {hoverEvents.map(ev => (
            <div key={ev.kind} style={{ color: ev.kind === 'earnings' ? 'var(--marker)' : 'var(--accent)', marginTop: 2 }}>
              {ev.label}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
