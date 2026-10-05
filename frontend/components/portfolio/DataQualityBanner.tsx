'use client';

import React from 'react';
import type { PositionMetrics } from '@/lib/portfolio';
import { plural } from '@/lib/format';
import s from './portfolio.module.css';

export default function DataQualityBanner({ unpriced }: { unpriced: PositionMetrics[] }) {
  if (unpriced.length === 0) return null;
  const tickers = unpriced.map(r => r.position.asset.ticker).join(', ');

  return (
    <div className={s.banner} role="status">
      <svg className={s.bannerIcon} width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M8 5.5v3.2M8 11h.01M6.9 2.2 1.5 12.2A1.2 1.2 0 0 0 2.6 14h10.8a1.2 1.2 0 0 0 1.1-1.8L9.1 2.2a1.2 1.2 0 0 0-2.2 0Z"
          stroke="currentColor"
          strokeWidth="1.3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span>
        <b>
          {unpriced.length} {plural(unpriced.length, 'pozycja', 'pozycje', 'pozycji')} bez danych
          rynkowych
        </b>{' '}
        ({tickers}) —{' '}
        {plural(unpriced.length, 'nie wchodzi', 'nie wchodzą', 'nie wchodzi')} do wartości portfela ani
        do wyniku. Snapshot pojawi się po najbliższym cyklu zbierania danych albo po ręcznym odświeżeniu
        notowań.
      </span>
    </div>
  );
}
