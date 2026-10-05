'use client';

import React from 'react';
import { MONO } from '@/lib/format';

export interface DonutSlice {
  label: string;
  value: number;
  color: string;
}

interface DonutChartProps {
  slices: DonutSlice[];
  centerValue: string;
  centerLabel: string;
  size?: number;
  ariaLabel: string;
}

const RADIUS = 58;
const STROKE = 20;
const VIEWBOX = 160;
const GAP = 1.5;

export default function DonutChart({
  slices,
  centerValue,
  centerLabel,
  size = 158,
  ariaLabel,
}: DonutChartProps) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  const center = VIEWBOX / 2;
  const circumference = 2 * Math.PI * RADIUS;

  let offset = 0;
  const segments = slices.map((slice, i) => {
    const length = (slice.value / total) * circumference;
    const dash = Math.max(length - GAP, 0);
    const segment = (
      <circle
        key={`${slice.label}-${i}`}
        cx={center}
        cy={center}
        r={RADIUS}
        fill="none"
        stroke={slice.color}
        strokeWidth={STROKE}
        strokeDasharray={`${dash.toFixed(2)} ${(circumference - dash).toFixed(2)}`}
        strokeDashoffset={(-offset).toFixed(2)}
        transform={`rotate(-90 ${center} ${center})`}
      />
    );
    offset += length;
    return segment;
  });

  return (
    <svg
      viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
      style={{ width: size, height: size, flexShrink: 0 }}
      role="img"
      aria-label={ariaLabel}
    >
      <circle cx={center} cy={center} r={RADIUS} fill="none" stroke="var(--chart-grid)" strokeWidth={STROKE} />
      {total > 0 && segments}
      <text
        x={center}
        y={center - 4}
        textAnchor="middle"
        fontSize="20"
        fontWeight="700"
        style={{ fill: 'var(--fg)', fontFamily: MONO }}
      >
        {centerValue}
      </text>
      <text
        x={center}
        y={center + 12}
        textAnchor="middle"
        fontSize="8"
        letterSpacing="1"
        style={{ fill: 'var(--chart-axis)' }}
      >
        {centerLabel}
      </text>
    </svg>
  );
}
