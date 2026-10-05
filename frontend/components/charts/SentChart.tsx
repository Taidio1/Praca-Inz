'use client';

import React from 'react';
import { sentColor, MONO } from '@/lib/format';

export interface SentPoint {
  /* ISO timestamp insightu */
  t: string;
  score: number;
}

/* Historia sentymentu z realnych insightów; punkty równomiernie po osi indeksu
   (odstępy czasowe między insightami bywają nieregularne). */
export default function SentChart({ points }: { points: SentPoint[] }) {
  if (points.length < 2) {
    return (
      <div style={{ padding: '18px 0', fontSize: 11.5, color: 'var(--muted-2)', fontStyle: 'italic' }}>
        Za mało insightów, by narysować historię sentymentu (potrzebne co najmniej 2).
      </div>
    );
  }

  const sorted = [...points].sort((a, b) => new Date(a.t).getTime() - new Date(b.t).getTime());
  const data = sorted.map(p => Math.max(-1, Math.min(1, p.score)));
  const last = data[data.length - 1];
  const n = data.length;

  const W = 560,
    H = 80,
    pl = 28,
    pr = 14,
    pt = 10,
    pb = 18;
  const iW = W - pl - pr,
    iH = H - pt - pb;
  const xS = (i: number) => (i / (n - 1)) * iW;
  const yS = (v: number) => iH / 2 - v * (iH / 2);
  const pth = data.map((v, i) => `${i ? 'L' : 'M'}${xS(i).toFixed(1)},${yS(v).toFixed(1)}`).join('');
  const col = sentColor(last);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: '100%', height: 'auto', display: 'block', minWidth: 250 }}
      role="img"
      aria-label="Historia sentymentu"
    >
      <g transform={`translate(${pl},${pt})`}>
        <line
          x1="0"
          y1={(iH / 2).toFixed(1)}
          x2={iW.toFixed(1)}
          y2={(iH / 2).toFixed(1)}
          style={{ stroke: 'var(--chart-zero)' }}
          strokeWidth="1"
          strokeDasharray="4,3"
        />
        <path d={pth} fill="none" style={{ stroke: col }} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        {data.map((v, i) => (
          <circle key={i} cx={xS(i).toFixed(1)} cy={yS(v).toFixed(1)} r={i === n - 1 ? 4 : 2.5} style={{ fill: sentColor(v) }} />
        ))}
        <text x="-4" y="4" textAnchor="end" fontSize="8" style={{ fill: 'var(--pos)', fontFamily: MONO }}>
          +1
        </text>
        <text x="-4" y={(iH / 2 + 3).toFixed(1)} textAnchor="end" fontSize="8" style={{ fill: 'var(--chart-axis)', fontFamily: MONO }}>
          0
        </text>
        <text x="-4" y={(iH + 2).toFixed(1)} textAnchor="end" fontSize="8" style={{ fill: 'var(--neg)', fontFamily: MONO }}>
          -1
        </text>
      </g>
    </svg>
  );
}
