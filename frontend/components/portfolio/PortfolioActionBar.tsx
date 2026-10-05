'use client';

import React, { useState } from 'react';
import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';
import { useApp } from '@/lib/store';
import { formatTime, plural } from '@/lib/format';
import s from './portfolio.module.css';

interface PortfolioActionBarProps {
  positionCount: number;
  assetClassCount: number;
  lastCapturedAt: string | null;
  onAdd: () => void;
}

export default function PortfolioActionBar({
  positionCount,
  assetClassCount,
  lastCapturedAt,
  onAdd,
}: PortfolioActionBarProps) {
  const { refreshPortfolio, showToast } = useApp();
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      const { refreshed } = await api.refreshPrices();
      await refreshPortfolio();
      showToast(
        refreshed > 0 ? `Zaktualizowano notowania ${refreshed} aktywów` : 'Brak aktywów do odświeżenia',
      );
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : 'Nie udało się odświeżyć notowań.');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className={s.actionBar}>
      <div className={s.actionMeta}>
        <div className={s.eyebrow}>Stan portfela</div>
        <div className={s.stamp}>
          {lastCapturedAt ? `Notowania: ${formatTime(lastCapturedAt)}` : 'Brak snapshotu notowań'} ·{' '}
          {positionCount} {plural(positionCount, 'pozycja', 'pozycje', 'pozycji')} · {assetClassCount}{' '}
          {plural(assetClassCount, 'klasa', 'klasy', 'klas')} aktywów
        </div>
      </div>
      <button type="button" className={s.btnGhost} onClick={() => void refresh()} disabled={refreshing}>
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <path
            d="M12.5 7a5.5 5.5 0 1 1-1.6-3.9M12.5 1v3.5H9"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {refreshing ? 'Odświeżanie…' : 'Odśwież notowania'}
      </button>
      <button type="button" className={s.btnPrimary} onClick={onAdd}>
        <svg width="14" height="14" viewBox="0 0 15 15" fill="none" aria-hidden="true">
          <path d="M7.5 2v11M2 7.5h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        Dodaj aktywo
      </button>
    </div>
  );
}
