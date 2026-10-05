'use client';

import React from 'react';
import type { PricePoint } from '@/lib/types';

interface SparklineProps {
  points: PricePoint[];
  width?: number;
  height?: number;
}

export default function Sparkline({ points, width = 64, height = 20 }: SparklineProps) {
  if (points.length < 2) return null;

  const prices = points.map(p => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const rising = prices[prices.length - 1] >= prices[0];

  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * (width - 2) + 1;
      const y = height - 1 - ((p.price - min) / span) * (height - 2);
      return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join('');

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" focusable="false">
      <path
        d={d}
        fill="none"
        stroke={rising ? 'var(--pos)' : 'var(--neg)'}
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
