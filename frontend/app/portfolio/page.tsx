'use client';

import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';
import { useApp } from '@/lib/store';
import { computePortfolioMetrics, type PositionMetrics } from '@/lib/portfolio';
import type { AssetType, PortfolioHistory } from '@/lib/types';
import { ASSET_GROUPS } from '@/components/SidebarPortfolioGroups';
import PortfolioValueChart, { type HistoryRange } from '@/components/charts/PortfolioValueChart';
import AddPositionDialog from '@/components/portfolio/AddPositionDialog';
import AttentionList from '@/components/portfolio/AttentionList';
import ConfirmDialog from '@/components/portfolio/ConfirmDialog';
import DataQualityBanner from '@/components/portfolio/DataQualityBanner';
import ExposurePanel from '@/components/portfolio/ExposurePanel';
import MoversStrip from '@/components/portfolio/MoversStrip';
import PortfolioActionBar from '@/components/portfolio/PortfolioActionBar';
import PortfolioKpis from '@/components/portfolio/PortfolioKpis';
import PositionsTable from '@/components/portfolio/PositionsTable';
import s from '@/components/portfolio/portfolio.module.css';

const EMPTY_HISTORY: PortfolioHistory = {
  points: [],
  skipped_tickers: [],
  base_currency: '',
  fx_rate_date: null,
  fx_sources: [],
};

function PageSkeleton() {
  return (
    <div className={s.page}>
      <div className={s.kpis}>
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className={i === 0 ? s.kpiHero : s.kpi}>
            <div className={s.skeleton} style={{ height: 10, width: '60%' }} />
            <div className={s.skeleton} style={{ height: i === 0 ? 30 : 22, width: '75%' }} />
            <div className={s.skeleton} style={{ height: 10, width: '45%' }} />
          </div>
        ))}
      </div>
      <div className={s.card}>
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className={s.skeletonRow}>
            <div className={s.skeleton} style={{ width: 38, height: 38, borderRadius: 9 }} />
            <div className={s.skeleton} style={{ height: 12, flex: 1 }} />
            <div className={s.skeleton} style={{ height: 12, width: 90 }} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PortfolioPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <PortfolioView />
    </Suspense>
  );
}

function PortfolioView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { positions: allPositions, portfolioLoading, portfolioError, removeAsset, baseCurrency } = useApp();

  const typeParam = searchParams.get('type');
  const typeFilter = typeParam && typeParam in ASSET_GROUPS ? (typeParam as AssetType) : null;
  const positions = useMemo(
    () => (typeFilter ? allPositions.filter(p => p.asset.asset_type === typeFilter) : allPositions),
    [allPositions, typeFilter],
  );

  const [adding, setAdding] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PositionMetrics | null>(null);
  const [range, setRange] = useState<HistoryRange>(90);
  const [history, setHistory] = useState<PortfolioHistory>(EMPTY_HISTORY);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const metrics = useMemo(() => computePortfolioMetrics(positions), [positions]);
  const assetClassCount = useMemo(
    () => new Set(positions.map(p => p.asset.asset_type)).size,
    [positions],
  );

  useEffect(() => {
    if (positions.length === 0) {
      setHistory(EMPTY_HISTORY);
      setHistoryLoading(false);
      return;
    }
    if (typeFilter) {
      // Historia wartości z API dotyczy całego portfela, więc przy filtrze grupy jej nie pokazujemy.
      setHistoryLoading(false);
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    setHistoryError(null);
    api
      .getPortfolioHistory(range)
      .then(data => {
        if (!cancelled) setHistory(data);
      })
      .catch(e => {
        if (cancelled) return;
        setHistory(EMPTY_HISTORY);
        setHistoryError(
          e instanceof ApiError ? e.message : 'Nie udało się pobrać historii wartości portfela.',
        );
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range, positions.length, typeFilter, baseCurrency]);

  if (portfolioLoading) return <PageSkeleton />;

  if (portfolioError) {
    return (
      <div className={s.errorBox}>
        <p style={{ fontSize: 13.5, color: 'var(--neg)', marginBottom: 6 }}>{portfolioError}</p>
        <p style={{ fontSize: 11, color: 'var(--faint)' }}>
          Upewnij się, że backend API działa (http://localhost:8000).
        </p>
      </div>
    );
  }

  if (positions.length === 0 && typeFilter) {
    return (
      <div className={s.errorBox}>
        <p style={{ fontSize: 13.5, color: 'var(--fg-2)', marginBottom: 10 }}>
          Brak pozycji w grupie {ASSET_GROUPS[typeFilter].label}.
        </p>
        <button type="button" className={s.btnPrimary} onClick={() => router.push('/portfolio')}>
          Pokaż cały portfel
        </button>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <>
        <div className={s.empty}>
          <div className={s.emptyIcon}>
            <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <path
                d="M4 26L10 12L18 20L28 6"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <h2 className={s.emptyTitle}>Portfel jest pusty</h2>
          <p className={s.emptyText}>
            Dodaj pierwsze aktywo, aby zobaczyć wycenę pozycji, strukturę ekspozycji i informacje
            dopasowane do tego, co faktycznie posiadasz.
          </p>
          <button type="button" className={s.btnPrimary} onClick={() => setAdding(true)}>
            Dodaj pierwsze aktywo
          </button>
          <p className={s.disclaimer} style={{ marginTop: 24, maxWidth: 320, textAlign: 'center' }}>
            Materiał informacyjny i edukacyjny — nie stanowi porady inwestycyjnej.
          </p>
        </div>
        {adding && <AddPositionDialog positions={positions} onClose={() => setAdding(false)} />}
      </>
    );
  }

  return (
    <>
      <div className={s.page}>
        <PortfolioActionBar
          positionCount={positions.length}
          assetClassCount={assetClassCount}
          lastCapturedAt={metrics.lastCapturedAt}
          onAdd={() => setAdding(true)}
        />

        {typeFilter && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--muted)' }}>
            <span>Widok grupy:</span>
            <button
              type="button"
              onClick={() => router.push('/portfolio')}
              title="Pokaż cały portfel"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '3px 10px',
                borderRadius: 20,
                border: '1px solid var(--accent-line)',
                background: 'var(--accent-soft)',
                color: 'var(--fg)',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {ASSET_GROUPS[typeFilter].label}
              <span aria-hidden="true" style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1 }}>×</span>
            </button>
            <span>udziały i KPI liczone w obrębie tej grupy</span>
          </div>
        )}

        <PortfolioKpis metrics={metrics} />

        <DataQualityBanner unpriced={metrics.unpriced} />

        {typeFilter ? (
          <ExposurePanel priced={metrics.priced} />
        ) : (
          <div className={s.grid2}>
            <PortfolioValueChart
              points={history.points}
              skippedTickers={history.skipped_tickers}
              currency={history.base_currency || baseCurrency}
              fxDate={history.fx_rate_date}
              fxSources={history.fx_sources}
              range={range}
              onRangeChange={setRange}
              loading={historyLoading}
              error={historyError}
            />
            <ExposurePanel priced={metrics.priced} />
          </div>
        )}

        <PositionsTable rows={metrics.rows} onDelete={setPendingDelete} />

        <div className={s.grid3}>
          <MoversStrip priced={metrics.priced} />
          <AttentionList metrics={metrics} />
        </div>

        <p className={s.disclaimer}>
          Wyceny pochodzą z ostatniego snapshotu rynkowego i mają charakter informacyjny — nie stanowią
          porady inwestycyjnej.
        </p>
      </div>

      {adding && <AddPositionDialog positions={allPositions} onClose={() => setAdding(false)} />}

      {pendingDelete && (
        <ConfirmDialog
          title={`Usunąć pozycję ${pendingDelete.position.asset.ticker}?`}
          description={
            <>
              Usunięte zostaną wszystkie transakcje tej pozycji wraz z jej historią w portfelu. Insighty i
              ślad audytowy pozostaną w bazie. Tej operacji nie można cofnąć.
            </>
          }
          confirmLabel="Usuń pozycję"
          pendingLabel="Usuwanie…"
          onConfirm={async () => {
            await removeAsset(pendingDelete.id);
            setPendingDelete(null);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </>
  );
}
