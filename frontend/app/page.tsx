'use client';

import React, { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useApp } from '@/lib/store';
import { computePortfolioMetrics } from '@/lib/portfolio';
import { ASSET_TYPE_LABELS } from '@/lib/types';
import { fmtCurrency, fmtSignedPct, formatPrice, MONO } from '@/lib/format';
import FxNote from '@/components/portfolio/FxNote';
import ExposurePanel from '@/components/portfolio/ExposurePanel';

export default function DashboardPage() {
  const router = useRouter();
  const { positions, portfolioLoading, portfolioError } = useApp();
  const metrics = useMemo(() => computePortfolioMetrics(positions), [positions]);

  if (portfolioLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '72px 24px', color: 'var(--muted-2)', fontSize: 13 }}>
        Ładowanie portfela…
      </div>
    );
  }

  if (portfolioError) {
    return (
      <div style={{ textAlign: 'center', padding: '72px 24px' }}>
        <p style={{ fontSize: 13.5, color: 'var(--neg)', marginBottom: 6 }}>{portfolioError}</p>
        <p style={{ fontSize: 11, color: 'var(--faint)' }}>Upewnij się, że backend API działa (http://localhost:8000).</p>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '72vh',
          padding: '40px 24px',
          textAlign: 'center',
          animation: 'fadeUp .4s ease',
        }}
      >
        <div
          style={{
            width: 68,
            height: 68,
            background: 'linear-gradient(135deg,var(--accent),var(--accent-2))',
            borderRadius: 18,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: 22,
            boxShadow: '0 12px 36px var(--accent-line)',
            color: 'var(--on-accent)',
          }}
        >
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
            <path d="M4 26L10 12L18 20L28 6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg)', marginBottom: 10, letterSpacing: -0.5 }}>Witaj w Opes</h2>
        <p style={{ fontSize: 14, color: 'var(--muted)', maxWidth: 330, lineHeight: 1.65, marginBottom: 28 }}>
          Dodaj pierwsze aktywa do portfela, aby zacząć śledzić spersonalizowane informacje i analizy sentymentu.
        </p>
        <button
          type="button"
          onClick={() => router.push('/portfolio')}
          style={{
            background: 'linear-gradient(135deg,var(--accent),var(--accent-2))',
            color: 'var(--on-accent)',
            border: 'none',
            borderRadius: 10,
            padding: '12px 28px',
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
            boxShadow: '0 6px 20px var(--accent-glow)',
            fontFamily: 'inherit',
          }}
        >
          Dodaj pierwsze aktywo
        </button>
        <p style={{ marginTop: 24, fontSize: 10, color: 'var(--faint-2)', fontStyle: 'italic', maxWidth: 300, lineHeight: 1.5 }}>
          Materiał informacyjny i edukacyjny — nie stanowi porady inwestycyjnej.
        </p>
      </div>
    );
  }

  /* Wartości liczone wyłącznie z realnych snapshotów; pozycje bez ceny nie wchodzą do sumy. */
  const { totalValue: total, dayPct: changePct, priced } = metrics;
  const changePos = (changePct ?? 0) >= 0;
  const hasMarketData = priced.length > 0;

  return (
    <div style={{ padding: '14px 14px 2px', display: 'flex', flexDirection: 'column', gap: 11 }}>
      {/* Value hero */}
      <div style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 14, padding: '16px 14px', animation: 'fadeUp .3s ease' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
              Wartość portfela
            </div>
            {hasMarketData ? (
              <>
                <div style={{ fontFamily: MONO, fontSize: 28, fontWeight: 700, color: 'var(--fg)', lineHeight: 1, letterSpacing: -0.5 }}>
                  {fmtCurrency(total, metrics.baseCurrency)}
                </div>
                {metrics.fx && <FxNote date={metrics.fx.date} sources={metrics.fx.sources} style={{ marginTop: 5 }} />}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                  <span
                    className="num"
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      fontFamily: MONO,
                      color: changePos ? 'var(--pos)' : 'var(--neg)',
                      background: changePos ? 'var(--pos-soft)' : 'var(--neg-soft)',
                      border: `1px solid ${changePos ? 'var(--pos-line)' : 'var(--neg-line)'}`,
                      padding: '2px 8px',
                      borderRadius: 6,
                    }}
                  >
                    {fmtSignedPct(changePct)}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--muted-2)' }}>za 24h</span>
                </div>
                {priced.length < positions.length && (
                  <div style={{ fontSize: 10, color: 'var(--faint)', marginTop: 6, fontStyle: 'italic' }}>
                    Część pozycji nie ma jeszcze danych rynkowych — wartość jest niepełna.
                  </div>
                )}
              </>
            ) : (
              <div style={{ fontSize: 12, color: 'var(--muted-2)', lineHeight: 1.5, maxWidth: 420 }}>
                Brak danych rynkowych — silnik zbierania danych nie zapisał jeszcze żadnego snapshotu cen dla aktywów w portfelu.
              </div>
            )}
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div style={{ fontSize: 9, color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 3 }}>Aktywa</div>
            <div style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700, color: 'var(--fg-2)' }}>{positions.length}</div>
          </div>
        </div>
      </div>

      {hasMarketData && <ExposurePanel priced={priced} />}

      {/* Holdings mini list */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8 }}>Twój portfel</div>
          <button
            type="button"
            onClick={() => router.push('/portfolio')}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--accent)',
              fontSize: 11.5,
              fontWeight: 600,
              cursor: 'pointer',
              padding: 0,
              fontFamily: 'inherit',
              display: 'flex',
              alignItems: 'center',
              gap: 3,
            }}
          >
            Zarządzaj
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
              <path d="M4 2.5l4 3.5-4 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {positions.map(p => {
            const price = p.snapshot?.price ?? null;
            const change = p.snapshot?.change_24h ?? null;
            const pos = (change ?? 0) >= 0;
            const v = p.current_value; // w walucie bazowej
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => router.push(`/asset/${p.asset.id}`)}
                style={{
                  background: 'var(--panel)',
                  border: '1px solid var(--border)',
                  borderRadius: 11,
                  padding: '11px 13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 11,
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontFamily: 'inherit',
                  width: '100%',
                }}
              >
                <div
                  style={{
                    width: 36,
                    height: 36,
                    background: 'linear-gradient(135deg,var(--border),var(--panel-2))',
                    borderRadius: 8,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    border: '1px solid var(--border-2)',
                  }}
                >
                  <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 500, color: 'var(--fg-2)' }}>{p.asset.ticker}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>{p.asset.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--muted-2)', fontFamily: MONO, marginTop: 2 }}>
                    {p.quantity} {p.asset.ticker} · {formatPrice(price, p.currency)} · {ASSET_TYPE_LABELS[p.asset.asset_type]}
                  </div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontFamily: MONO, fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>{fmtCurrency(v, p.base_currency)}</div>
                  {change != null && (
                    <div style={{ fontSize: 11, fontWeight: 600, color: pos ? 'var(--pos)' : 'var(--neg)', marginTop: 2 }}>
                      {(pos ? '+' : '') + change.toFixed(2)}%
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <button
        type="button"
        onClick={() => router.push('/feed')}
        style={{
          width: '100%',
          background: 'var(--panel)',
          border: '1px solid var(--border)',
          borderRadius: 12,
          padding: '13px 14px',
          color: 'var(--accent)',
          fontSize: 13,
          fontWeight: 600,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 7,
          fontFamily: 'inherit',
          marginTop: 2,
        }}
      >
        Zobacz strumień informacji
        <svg width="13" height="13" viewBox="0 0 12 12" fill="none">
          <path d="M4 2.5l4 3.5-4 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}
