'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import type { PortfolioMetrics, PositionMetrics } from '@/lib/portfolio';
import { sentLabel } from '@/lib/format';
import s from './portfolio.module.css';

interface AttentionItem {
  key: string;
  color: string;
  assetId: string;
  ticker: string;
  reason: string;
}

const NEGATIVE_SENTIMENT = -0.15;

function collect(metrics: PortfolioMetrics): AttentionItem[] {
  const item = (row: PositionMetrics, color: string, reason: string): AttentionItem => ({
    key: `${row.id}-${reason}`,
    color,
    assetId: row.position.asset.id,
    ticker: row.position.asset.ticker,
    reason,
  });

  return [
    ...metrics.priced
      .filter(row => row.sentiment != null && row.sentiment < NEGATIVE_SENTIMENT)
      .sort((a, b) => (a.sentiment ?? 0) - (b.sentiment ?? 0))
      .map(row =>
        item(
          row,
          'var(--neg)',
          `sentyment ${(row.sentiment ?? 0).toFixed(2)} — ${sentLabel(row.sentiment ?? 0).toLowerCase()}`,
        ),
      ),
    ...metrics.unpriced.map(row =>
      item(
        row,
        'var(--marker)',
        row.price == null ? 'brak snapshotu cenowego' : `brak kursu ${row.currency}/${metrics.baseCurrency}`,
      ),
    ),
    ...metrics.priced
      .filter(row => row.sentiment == null)
      .map(row => item(row, 'var(--muted)', 'brak analizy LLM')),
  ];
}

export default function AttentionList({ metrics }: { metrics: PortfolioMetrics }) {
  const router = useRouter();
  const items = collect(metrics).slice(0, 5);

  return (
    <section className={s.card}>
      <div className={s.cardHeadPlain}>
        <div className={s.eyebrow}>Wymaga uwagi</div>
      </div>
      <div className={s.attn}>
        {items.length === 0 ? (
          <p className={s.hint} style={{ marginTop: 0 }}>
            Każda pozycja ma aktualne notowanie i analizę o neutralnym lub pozytywnym wydźwięku.
          </p>
        ) : (
          items.map(item => (
            <button
              key={item.key}
              type="button"
              className={s.attnButton}
              onClick={() => router.push(`/asset/${item.assetId}`)}
            >
              <span className={s.attnDot} style={{ background: item.color }} aria-hidden="true" />
              <span>
                <b className="mono">{item.ticker}</b> — {item.reason}
              </span>
            </button>
          ))
        )}
        <button type="button" className={s.attnLink} onClick={() => router.push('/feed')}>
          Zobacz strumień informacji →
        </button>
      </div>
    </section>
  );
}
