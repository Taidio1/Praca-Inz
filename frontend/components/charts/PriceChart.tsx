'use client';

import React, { useMemo, useState } from 'react';
import { MONO, formatPrice } from '@/lib/format';
import type { PortfolioTransaction, PricePoint } from '@/lib/types';

export type PriceRange = 30 | 90 | 365;

const RANGES: PriceRange[] = [30, 90, 365];

interface PriceChartProps {
  currency: string; // waluta notowania: oś cen i znaczniki transakcji
  points: PricePoint[];
  transactions: PortfolioTransaction[];
  range: PriceRange;
  onRangeChange: (range: PriceRange) => void;
  unit?: string; // jednostka ilości w znacznikach transakcji
}

function rangeBtnStyle(active: boolean): React.CSSProperties {
  return {
    background: active ? 'var(--accent-soft)' : 'var(--bg-inset)',
    border: `1px solid ${active ? 'var(--accent-line)' : 'var(--border)'}`,
    color: active ? 'var(--accent)' : 'var(--muted-2)',
    borderRadius: 6,
    padding: '4px 10px',
    fontSize: 11,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
  };
}

function formatAxisDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit' });
}

/* Linia dziennego close + markery zakupów pozycjonowane po dacie; brak linii break-even (poza zakresem MVP). */
export default function PriceChart({
  currency,
  points,
  transactions,
  range,
  onRangeChange,
  unit = 'szt.',
}: PriceChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const sorted = useMemo(
    () => [...points].sort((a, b) => a.price_date.localeCompare(b.price_date)),
    [points],
  );

  const switcher = (
    <div style={{ display: 'flex', gap: 6, marginBottom: 11 }}>
      {RANGES.map(r => (
        <button key={r} type="button" onClick={() => onRangeChange(r)} style={rangeBtnStyle(r === range)}>
          {r} dni
        </button>
      ))}
    </div>
  );

  if (sorted.length < 2) {
    return (
      <div>
        {switcher}
        <div style={{ padding: '18px 0', fontSize: 11.5, color: 'var(--muted-2)', fontStyle: 'italic' }}>
          Za mało danych cenowych, by narysować wykres (potrzebne co najmniej 2 punkty).
        </div>
      </div>
    );
  }

  const dates = sorted.map(p => new Date(p.price_date).getTime());
  const minDate = dates[0];
  const maxDate = dates[dates.length - 1];

  const markers = transactions
    .map(t => ({ tx: t, time: new Date(t.purchased_at).getTime() }))
    .filter(m => m.time >= minDate && m.time <= maxDate);

  const linePrices = sorted.map(p => p.price);
  // Znaczniki na osi ceny w walucie notowania (transakcja w innej walucie po kursie z dnia zakupu).
  const markerPrices = markers.map(m => m.tx.price_in_quote).filter((p): p is number => p != null);
  const allPrices = [...linePrices, ...markerPrices];
  const minPrice = Math.min(...allPrices);
  const maxPrice = Math.max(...allPrices);
  const priceSpan = maxPrice - minPrice || 1;

  const W = 560,
    H = 190,
    pl = 46,
    pr = 12,
    pt = 12,
    pb = 22;
  const iW = W - pl - pr,
    iH = H - pt - pb;

  const xScale = (time: number) =>
    maxDate === minDate ? iW / 2 : ((time - minDate) / (maxDate - minDate)) * iW;
  const yScale = (price: number) => iH - ((price - minPrice) / priceSpan) * iH;

  const path = sorted
    .map(
      (p, i) =>
        `${i ? 'L' : 'M'}${xScale(new Date(p.price_date).getTime()).toFixed(1)},${yScale(p.price).toFixed(1)}`,
    )
    .join('');

  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const hovered = hoverIdx != null ? markers[hoverIdx] : null;

  return (
    <div>
      {switcher}
      <div style={{ position: 'relative' }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: '100%', height: 'auto', display: 'block', minWidth: 250 }}
          role="img"
          aria-label="Wykres ceny"
        >
          <g transform={`translate(${pl},${pt})`}>
            <line
              x1="0"
              y1={yScale(maxPrice).toFixed(1)}
              x2={iW.toFixed(1)}
              y2={yScale(maxPrice).toFixed(1)}
              stroke="var(--chart-axis)"
              strokeWidth="1"
              strokeDasharray="3,3"
              opacity={0.3}
            />
            <line
              x1="0"
              y1={yScale(minPrice).toFixed(1)}
              x2={iW.toFixed(1)}
              y2={yScale(minPrice).toFixed(1)}
              stroke="var(--chart-axis)"
              strokeWidth="1"
              strokeDasharray="3,3"
              opacity={0.3}
            />
            <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            {markers.map((m, i) => (
              <circle
                key={m.tx.id}
                cx={xScale(m.time).toFixed(1)}
                cy={yScale(m.tx.price_in_quote ?? last.price).toFixed(1)}
                r={hoverIdx === i ? 6 : 4.5}
                fill="var(--marker)"
                stroke="var(--bg)"
                strokeWidth="1.5"
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoverIdx(i)}
                onMouseLeave={() => setHoverIdx(null)}
              />
            ))}
            <text x="-6" y={(yScale(maxPrice) + 3).toFixed(1)} textAnchor="end" fontSize="8" style={{ fill: 'var(--faint)', fontFamily: MONO }}>
              {formatPrice(maxPrice, currency)}
            </text>
            <text x="-6" y={(yScale(minPrice) + 3).toFixed(1)} textAnchor="end" fontSize="8" style={{ fill: 'var(--faint)', fontFamily: MONO }}>
              {formatPrice(minPrice, currency)}
            </text>
            <text x="0" y={(iH + 14).toFixed(1)} fontSize="8" style={{ fill: 'var(--faint)', fontFamily: MONO }}>
              {formatAxisDate(first.price_date)}
            </text>
            <text x={iW.toFixed(1)} y={(iH + 14).toFixed(1)} textAnchor="end" fontSize="8" style={{ fill: 'var(--faint)', fontFamily: MONO }}>
              {formatAxisDate(last.price_date)}
            </text>
          </g>
        </svg>
        {hovered && (
          <div
            style={{
              position: 'absolute',
              left: `${((pl + xScale(hovered.time)) / W) * 100}%`,
              top: `${((pt + yScale(hovered.tx.price_in_quote ?? last.price)) / H) * 100}%`,
              transform: 'translate(-50%, -135%)',
              background: 'var(--panel)',
              border: '1px solid var(--border-2)',
              borderRadius: 7,
              padding: '5px 8px',
              fontSize: 10.5,
              color: 'var(--fg)',
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
              zIndex: 5,
              boxShadow: '0 4px 14px rgba(0,0,0,.3)',
            }}
          >
            <div style={{ fontWeight: 600 }}>{hovered.tx.quantity.toLocaleString('pl-PL')} {unit}</div>
            <div style={{ color: 'var(--muted-2)' }}>
              {hovered.tx.price != null ? `po ${formatPrice(hovered.tx.price, hovered.tx.currency)}` : 'brak ceny'}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
