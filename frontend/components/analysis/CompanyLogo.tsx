'use client';

import React, { useState } from 'react';
import { logoColor } from '@/lib/analysisFormat';
import s from './analysis.module.css';

/* Logo z Finnhub, gdy jest; przy braku lub błędzie ładowania — monogram z tickera. */
export default function CompanyLogo({
  ticker,
  large = false,
  logoUrl = null,
}: {
  ticker: string;
  large?: boolean;
  logoUrl?: string | null;
}) {
  const [failed, setFailed] = useState(false);
  if (logoUrl && !failed) {
    return (
      <div className={large ? s.logoLg : s.logo} style={{ background: '#ffffff', padding: large ? 7 : 4 }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- zewnętrzny URL, bez optymalizacji Next */}
        <img
          src={logoUrl}
          alt={`Logo ${ticker}`}
          onError={() => setFailed(true)}
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      </div>
    );
  }
  const letters = ticker.replace(/[^A-Z]/gi, '').slice(0, large ? 2 : 1).toUpperCase() || '?';
  return (
    <div className={large ? s.logoLg : s.logo} style={{ background: logoColor(ticker) }} aria-hidden="true">
      {letters}
    </div>
  );
}
