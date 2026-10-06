'use client';

import React, { useMemo, useState } from 'react';
import DonutChart, { type DonutSlice } from '@/components/charts/DonutChart';
import type { PositionMetrics } from '@/lib/portfolio';
import { ASSET_TYPE_LABELS, type AssetType } from '@/lib/types';
import { CAT_COLORS, fmtCurrency } from '@/lib/format';
import s from './portfolio.module.css';

type ExposureMode = 'asset' | 'type';

const TYPE_COLORS: Record<AssetType, string> = {
  crypto: 'var(--cat1)',
  stock: 'var(--cat3)',
  etf: 'var(--cat4)',
  commodity: 'var(--cat5)',
};

export default function ExposurePanel({ priced }: { priced: PositionMetrics[] }) {
  // Wartości pozycji są już w walucie bazowej użytkownika.
  const base = priced.find(r => r.position.base_currency)?.position.base_currency ?? null;
  const [mode, setMode] = useState<ExposureMode>('asset');

  const slices: DonutSlice[] = useMemo(() => {
    if (mode === 'asset') {
      return [...priced]
        .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))
        .map((row, i) => ({
          label: row.position.asset.ticker,
          value: row.value ?? 0,
          color: CAT_COLORS[i % CAT_COLORS.length],
        }));
    }
    const byType = new Map<AssetType, number>();
    for (const row of priced) {
      const type = row.position.asset.asset_type;
      byType.set(type, (byType.get(type) ?? 0) + (row.value ?? 0));
    }
    return Array.from(byType.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, value]) => ({ label: ASSET_TYPE_LABELS[type], value, color: TYPE_COLORS[type] }));
  }, [priced, mode]);

  const total = slices.reduce((sum, slice) => sum + slice.value, 0);

  if (priced.length === 0) {
    return (
      <section className={s.card}>
        <div className={s.cardHead}>
          <div className={s.eyebrow}>Ekspozycja</div>
        </div>
        <p className={s.hint} style={{ padding: '18px 16px' }}>
          Brak wycenionych pozycji — struktura alokacji pojawi się po pierwszym snapshocie cen.
        </p>
      </section>
    );
  }

  return (
    <section className={s.card}>
      <div className={s.cardHead}>
        <div>
          <div className={s.eyebrow}>Ekspozycja</div>
          <div className={s.hint}>Udział w wartości rynkowej portfela</div>
        </div>
        <div className={s.seg} role="group" aria-label="Widok alokacji">
          <button
            type="button"
            className={s.segBtn}
            aria-pressed={mode === 'asset'}
            onClick={() => setMode('asset')}
          >
            Aktywa
          </button>
          <button
            type="button"
            className={s.segBtn}
            aria-pressed={mode === 'type'}
            onClick={() => setMode('type')}
          >
            Klasy
          </button>
        </div>
      </div>

      <div className={s.donutWrap}>
        <DonutChart
          slices={slices}
          centerValue={String(slices.length)}
          centerLabel={mode === 'asset' ? 'AKTYWA' : 'KLASY'}
          ariaLabel={
            mode === 'asset'
              ? `Alokacja portfela na ${slices.length} aktywów`
              : `Alokacja portfela na ${slices.length} klas aktywów`
          }
        />
      </div>

      {mode === 'type' && (
        <div className={s.typeBar} aria-hidden="true">
          {slices.map(slice => (
            <i key={slice.label} style={{ width: `${(slice.value / total) * 100}%`, background: slice.color }} />
          ))}
        </div>
      )}

      <div className={s.allocLegend}>
        {slices.map(slice => (
          <div key={slice.label} className={s.allocRow}>
            <span className={s.allocDot} style={{ background: slice.color }} />
            <span className="mono" style={{ color: 'var(--fg-2)' }}>
              {slice.label}
            </span>
            <span className={s.allocBar}>
              <i style={{ width: `${(slice.value / total) * 100}%`, background: slice.color }} />
            </span>
            <span className={`${s.allocPct} mono num`}>{((slice.value / total) * 100).toFixed(1)}%</span>
            <span className={`${s.allocValue} mono num`}>{fmtCurrency(slice.value, base)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
