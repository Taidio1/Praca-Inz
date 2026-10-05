'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useApp } from '@/lib/store';
import type { AssetType } from '@/lib/types';

/* Grupy portfela w panelu bocznym — budowane z prawdziwych pozycji, po typie aktywa.
 * Kolejność ustawiana przeciąganiem jest wygodą per przeglądarka (localStorage). */

export const ASSET_GROUPS: Record<AssetType, { label: string; badge: string; color: string }> = {
  stock: { label: 'Akcje', badge: 'AK', color: 'var(--cat1)' },
  etf: { label: 'ETF', badge: 'ET', color: 'var(--cat6)' },
  crypto: { label: 'Kryptowaluty', badge: 'KR', color: 'var(--cat4)' },
};

const DEFAULT_ORDER: AssetType[] = ['stock', 'etf', 'crypto'];
const ORDER_KEY = 'opes-nav-group-order';

function readOrder(): AssetType[] {
  try {
    const raw = localStorage.getItem(ORDER_KEY);
    if (!raw) return DEFAULT_ORDER;
    const saved = (JSON.parse(raw) as string[]).filter((t): t is AssetType => t in ASSET_GROUPS);
    return [...saved, ...DEFAULT_ORDER.filter(t => !saved.includes(t))];
  } catch {
    return DEFAULT_ORDER;
  }
}

function DragHandle() {
  return (
    <svg width="10" height="14" viewBox="0 0 10 14" fill="currentColor" aria-hidden="true">
      {[2, 7, 12].map(y => (
        <React.Fragment key={y}>
          <circle cx="2.5" cy={y} r="1.3" />
          <circle cx="7.5" cy={y} r="1.3" />
        </React.Fragment>
      ))}
    </svg>
  );
}

export default function SidebarPortfolioGroups() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { positions, portfolioLoading } = useApp();

  const [order, setOrder] = useState<AssetType[]>(DEFAULT_ORDER);
  const [dragging, setDragging] = useState<AssetType | null>(null);
  const [overType, setOverType] = useState<AssetType | null>(null);

  useEffect(() => setOrder(readOrder()), []);

  const counts = useMemo(() => {
    const c: Partial<Record<AssetType, number>> = {};
    for (const p of positions) c[p.asset.asset_type] = (c[p.asset.asset_type] ?? 0) + 1;
    return c;
  }, [positions]);

  const activeType = pathname.startsWith('/portfolio') ? searchParams.get('type') : null;
  const visible = order.filter(t => (counts[t] ?? 0) > 0);

  const drop = (target: AssetType) => {
    if (!dragging || dragging === target) return;
    const next = order.filter(t => t !== dragging);
    next.splice(next.indexOf(target), 0, dragging);
    setOrder(next);
    try {
      localStorage.setItem(ORDER_KEY, JSON.stringify(next));
    } catch {}
  };

  if (portfolioLoading) {
    return <p style={{ fontSize: 11.5, color: 'var(--faint)', padding: '6px 12px' }}>Wczytywanie…</p>;
  }

  if (visible.length === 0) {
    return (
      <button type="button" onClick={() => router.push('/portfolio')} style={emptyStyle}>
        Brak pozycji, dodaj pierwsze aktywo
      </button>
    );
  }

  return (
    <>
      {visible.map(t => {
        const g = ASSET_GROUPS[t];
        const active = activeType === t;
        return (
          <div
            key={t}
            draggable
            onDragStart={e => {
              setDragging(t);
              e.dataTransfer.effectAllowed = 'move';
            }}
            onDragOver={e => {
              e.preventDefault();
              setOverType(t);
            }}
            onDragLeave={() => setOverType(prev => (prev === t ? null : prev))}
            onDrop={e => {
              e.preventDefault();
              drop(t);
              setOverType(null);
            }}
            onDragEnd={() => {
              setDragging(null);
              setOverType(null);
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              borderRadius: 7,
              background: active ? 'var(--border)' : 'transparent',
              opacity: dragging === t ? 0.45 : 1,
              boxShadow: overType === t && dragging !== t ? 'inset 0 2px 0 var(--accent)' : 'none',
            }}
          >
            <button
              type="button"
              onClick={() => router.push(active ? '/portfolio' : `/portfolio?type=${t}`)}
              aria-current={active ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                flex: 1,
                minWidth: 0,
                padding: '8px 4px 8px 12px',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
                color: active ? 'var(--accent-2)' : 'var(--fg-2)',
                fontSize: 13.5,
                fontWeight: active ? 600 : 500,
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 18,
                  borderRadius: 4,
                  background: g.color,
                  color: '#0b0e13',
                  fontSize: 8.5,
                  fontWeight: 700,
                  letterSpacing: 0.2,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                {g.badge}
              </span>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{g.label}</span>
              <span className="num" style={{ fontSize: 10.5, color: 'var(--faint)' }}>
                {counts[t]}
              </span>
            </button>
            <span
              title="Przeciągnij, aby zmienić kolejność"
              style={{ padding: '8px 10px 8px 6px', color: 'var(--muted-2)', cursor: 'grab', display: 'flex' }}
            >
              <DragHandle />
            </span>
          </div>
        );
      })}
    </>
  );
}

const emptyStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  textAlign: 'left',
  fontSize: 11.5,
  color: 'var(--faint)',
  padding: '6px 12px',
};
