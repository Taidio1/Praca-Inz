'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import type { PositionMetrics } from '@/lib/portfolio';
import { fmtCurrency, fmtPriceExact, fmtSignedCurrency, fmtSignedPct } from '@/lib/format';
import s from './portfolio.module.css';

function MoverCard({ title, row }: { title: string; row: PositionMetrics }) {
  const router = useRouter();
  const positive = (row.change24h ?? 0) >= 0;
  const base = row.position.base_currency;

  return (
    <section className={s.card}>
      <div className={s.cardHeadPlain}>
        <div className={s.eyebrow}>{title}</div>
      </div>
      <div className={s.mover}>
        <div className={`${s.badge} mono`}>{row.position.asset.ticker}</div>
        <div className={s.moverText}>
          <div className={s.assetName}>{row.position.asset.name}</div>
          <div className={`${s.assetMeta} mono num`}>
            {fmtPriceExact(row.price, row.currency)} · {fmtCurrency(row.value, base)} w portfelu
          </div>
        </div>
        <div className={s.moverRight}>
          <div className={`${positive ? s.tagUp : s.tagDown} mono num`}>{fmtSignedPct(row.change24h)}</div>
          <div
            className="mono num"
            style={{ fontSize: 11, marginTop: 5, color: positive ? 'var(--pos)' : 'var(--neg)' }}
          >
            {fmtSignedCurrency(row.dayPl, base)}
          </div>
        </div>
      </div>
      <div style={{ padding: '0 16px 13px' }}>
        <button type="button" className={s.attnLink} onClick={() => router.push(`/asset/${row.position.asset.id}`)}>
          Zobacz szczegóły aktywa →
        </button>
      </div>
    </section>
  );
}

export default function MoversStrip({ priced }: { priced: PositionMetrics[] }) {
  const moved = priced
    .filter(row => row.change24h != null)
    .sort((a, b) => (b.change24h ?? 0) - (a.change24h ?? 0));

  if (moved.length === 0) return null;

  const gainer = moved[0];
  const loser = moved[moved.length - 1];

  return (
    <>
      <MoverCard title="Największy wzrost 24h" row={gainer} />
      {loser.id !== gainer.id && <MoverCard title="Największy spadek 24h" row={loser} />}
    </>
  );
}
