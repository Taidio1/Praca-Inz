'use client';

import React, { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Sparkline from '@/components/charts/Sparkline';
import { SentimentBar } from './PortfolioKpis';
import { useSparklines } from './useSparklines';
import type { PositionMetrics } from '@/lib/portfolio';
import { ASSET_TYPE_LABELS, type AssetType, type PricePoint } from '@/lib/types';
import {
  fmtPriceExact,
  fmtQty,
  fmtCurrency,
  fmtSignedCurrency,
  fmtSignedPct,
  sentColor,
  sentLabel,
} from '@/lib/format';
import FxNote from './FxNote';
import s from './portfolio.module.css';

type SortKey = 'name' | 'qty' | 'avg' | 'price' | 'chg' | 'value' | 'weight' | 'cost' | 'pl' | 'sent';
type Filter = AssetType | 'all';

const CHIP_CLASS: Record<AssetType, string> = {
  crypto: s.chipCrypto,
  stock: s.chipStock,
  etf: s.chipEtf,
};

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'Wszystkie' },
  { value: 'crypto', label: 'Krypto' },
  { value: 'stock', label: 'Akcje' },
  { value: 'etf', label: 'ETF' },
];

const COLUMNS: { key: SortKey | null; label: string; sortable: boolean }[] = [
  { key: 'name', label: 'Aktywo', sortable: true },
  { key: 'qty', label: 'Ilość', sortable: true },
  { key: 'avg', label: 'Śr. cena', sortable: true },
  { key: 'price', label: 'Cena', sortable: true },
  { key: 'chg', label: '24h', sortable: true },
  { key: null, label: 'Trend 30d', sortable: false },
  { key: 'value', label: 'Wartość', sortable: true },
  { key: 'weight', label: 'Udział', sortable: true },
  { key: 'cost', label: 'Koszt', sortable: true },
  { key: 'pl', label: 'Wynik', sortable: true },
  { key: 'sent', label: 'Sentyment', sortable: true },
  { key: null, label: '', sortable: false },
];

/* Kolumny w walucie bazowej; ceny (Śr. cena, Cena) zostają w walucie notowania pozycji. */
const BASE_COLUMNS = new Set<SortKey>(['value', 'cost', 'pl']);

function sortValue(row: PositionMetrics, key: SortKey): string | number | null {
  switch (key) {
    case 'name':
      return row.position.asset.name;
    case 'qty':
      return row.position.quantity;
    case 'avg':
      return row.position.avg_buy_price;
    case 'price':
      return row.price;
    case 'chg':
      return row.change24h;
    case 'value':
      return row.value;
    case 'weight':
      return row.weight;
    case 'cost':
      return row.cost;
    case 'pl':
      return row.plPct;
    case 'sent':
      return row.sentiment;
  }
}

function plColor(v: number | null): string {
  if (v == null || v === 0) return 'var(--fg-2)';
  return v > 0 ? 'var(--pos)' : 'var(--neg)';
}

interface PositionsTableProps {
  rows: PositionMetrics[];
  onDelete: (row: PositionMetrics) => void;
}

export default function PositionsTable({ rows, onDelete }: PositionsTableProps) {
  const router = useRouter();
  const [sortKey, setSortKey] = useState<SortKey>('value');
  const [ascending, setAscending] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');

  const assets = useMemo(() => rows.map(row => row.position.asset), [rows]);
  const sparklines = useSparklines(assets);

  const availableFilters = useMemo(() => {
    const present = new Set(rows.map(row => row.position.asset.asset_type));
    return FILTERS.filter(f => f.value === 'all' || present.has(f.value));
  }, [rows]);

  const visible = useMemo(() => {
    const direction = ascending ? 1 : -1;
    return rows
      .filter(row => filter === 'all' || row.position.asset.asset_type === filter)
      .slice()
      .sort((a, b) => {
        const av = sortValue(a, sortKey);
        const bv = sortValue(b, sortKey);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === 'string' && typeof bv === 'string') {
          return av.localeCompare(bv, 'pl') * direction;
        }
        return ((av as number) - (bv as number)) * direction;
      });
  }, [rows, filter, sortKey, ascending]);

  // Wartość, koszt i wynik są w walucie bazowej; ceny w walucie notowania danej pozycji.
  const base = rows.find(row => row.position.base_currency)?.position.base_currency ?? null;
  const fx = useMemo(() => {
    const converted = rows.filter(
      row => row.value != null && row.position.fx_rate_date && row.position.currency !== row.position.base_currency,
    );
    if (converted.length === 0) return null;
    return {
      date: converted.map(row => row.position.fx_rate_date as string).sort()[converted.length - 1],
      sources: Array.from(new Set(converted.map(row => row.position.fx_source ?? ''))).filter(Boolean),
    };
  }, [rows]);

  const totals = useMemo(() => {
    const priced = visible.filter(row => row.value != null);
    const value = priced.reduce((sum, row) => sum + (row.value ?? 0), 0);
    const cost = priced.reduce((sum, row) => sum + (row.cost ?? 0), 0);
    const weight = priced.reduce((sum, row) => sum + (row.weight ?? 0), 0);
    const withCost = priced.filter(row => row.cost != null);
    return {
      value,
      cost,
      weight,
      pl: withCost.length > 0 ? withCost.reduce((sum, row) => sum + (row.pl ?? 0), 0) : null,
    };
  }, [visible]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setAscending(prev => !prev);
      return;
    }
    setSortKey(key);
    setAscending(key === 'name');
  };

  const open = (row: PositionMetrics) => router.push(`/asset/${row.position.asset.id}`);

  const ariaSort = (key: SortKey | null): 'ascending' | 'descending' | 'none' | undefined => {
    if (key == null) return undefined;
    if (key !== sortKey) return 'none';
    return ascending ? 'ascending' : 'descending';
  };

  const deleteButton = (row: PositionMetrics) => (
    <button
      type="button"
      className={s.iconBtnDanger}
      aria-label={`Usuń pozycję ${row.position.asset.ticker}`}
      onClick={e => {
        e.stopPropagation();
        onDelete(row);
      }}
    >
      <svg width="13" height="13" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <path
          d="M1.5 2.5h9M4.5 2.5V1.5h3v1M9.5 2.5l-.6 7.5H3.1L2.5 2.5"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );

  const identity = (row: PositionMetrics) => (
    <div className={s.assetCell}>
      <div className={`${s.badge} mono`}>{row.position.asset.ticker}</div>
      <div>
        <div className={s.assetName}>{row.position.asset.name}</div>
        <div className={s.assetMeta}>
          <span className={CHIP_CLASS[row.position.asset.asset_type]}>
            {ASSET_TYPE_LABELS[row.position.asset.asset_type]}
          </span>
          <span className="mono num">{fmtQty(row.position.quantity)} szt.</span>
        </div>
      </div>
    </div>
  );

  const sentiment = (row: PositionMetrics) =>
    row.sentiment == null ? (
      <span className={s.noData}>brak analizy</span>
    ) : (
      <>
        <span className="mono num" style={{ color: sentColor(row.sentiment), fontWeight: 600 }}>
          {(row.sentiment < 0 ? '−' : '+') + Math.abs(row.sentiment).toFixed(2)}
        </span>
        <SentimentBar score={row.sentiment} />
      </>
    );

  const trend = (row: PositionMetrics) => {
    const points: PricePoint[] = sparklines.get(row.position.asset.id) ?? [];
    return points.length >= 2 ? <Sparkline points={points} /> : <span className={s.noData}>—</span>;
  };

  return (
    <section className={s.card}>
      <div className={s.cardHead}>
        <div>
          <div className={s.eyebrow}>Pozycje</div>
          <div className={s.hint}>Kliknij nagłówek, aby posortować · kliknij wiersz, aby otworzyć aktywo</div>
        </div>
        {availableFilters.length > 2 && (
          <div className={s.seg} role="group" aria-label="Filtr klasy aktywów">
            {availableFilters.map(f => (
              <button
                key={f.value}
                type="button"
                className={s.segBtn}
                aria-pressed={filter === f.value}
                onClick={() => setFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className={s.tableWrap}>
        <table className={s.table}>
          <caption className={s.srOnly}>
            Pozycje portfela: ilość, cena nabycia, wycena, udział, wynik i sentyment analizy LLM
          </caption>
          <thead>
            <tr>
              {COLUMNS.map(column => (
                <th key={column.label || 'actions'} scope="col" aria-sort={ariaSort(column.key)}>
                  {column.sortable && column.key ? (
                    <button type="button" className={s.sortBtn} onClick={() => toggleSort(column.key as SortKey)}>
                      {column.label}
                      {base && BASE_COLUMNS.has(column.key) ? ` (${base})` : ''}
                      <svg
                        className={
                          column.key === sortKey ? (ascending ? s.caretUp : s.caretActive) : s.caret
                        }
                        width="8"
                        height="8"
                        viewBox="0 0 8 8"
                        aria-hidden="true"
                      >
                        <path d="M1 2.5 4 6l3-3.5z" fill="currentColor" />
                      </svg>
                    </button>
                  ) : (
                    column.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map(row => (
              <tr
                key={row.id}
                className={s.row}
                tabIndex={0}
                onClick={() => open(row)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    open(row);
                  }
                }}
              >
                <td>{identity(row)}</td>
                <td className="mono num" style={{ color: 'var(--fg-3)' }}>
                  {fmtQty(row.position.quantity)}
                </td>
                <td className="mono num" style={{ color: 'var(--muted)' }}>
                  {fmtPriceExact(row.position.avg_buy_price, row.currency)}
                </td>
                <td className="mono num" style={{ color: 'var(--fg-2)', fontWeight: 600 }}>
                  {row.price == null ? <span className={s.noData}>brak</span> : fmtPriceExact(row.price, row.currency)}
                </td>
                <td className="mono num" style={{ color: plColor(row.change24h), fontWeight: 600 }}>
                  {fmtSignedPct(row.change24h)}
                </td>
                <td>{trend(row)}</td>
                <td className="mono num" style={{ color: 'var(--fg)', fontWeight: 600 }}>
                  {row.value == null ? (
                    row.price != null ? (
                      <span className={s.noData} title={`Brak kursu ${row.currency}/${base}`}>
                        brak kursu
                      </span>
                    ) : (
                      '—'
                    )
                  ) : (
                    fmtCurrency(row.value, base)
                  )}
                </td>
                <td>
                  <div className={s.weightCell}>
                    <span className="mono num" style={{ color: 'var(--fg-3)' }}>
                      {row.weight == null ? '—' : `${row.weight.toFixed(1)}%`}
                    </span>
                    <span className={s.meter} aria-hidden="true">
                      <i style={{ width: `${row.weight ?? 0}%` }} />
                    </span>
                  </div>
                </td>
                <td className="mono num" style={{ color: 'var(--muted)' }}>
                  {row.cost == null ? '—' : fmtCurrency(row.cost, base)}
                </td>
                <td>
                  <div
                    className="mono num"
                    style={{ color: plColor(row.pl), fontWeight: 600 }}
                    title={
                      row.plPrice != null && row.plFx != null && row.currency !== base
                        ? `Zmiana ceny: ${fmtSignedCurrency(row.plPrice, base)}, zmiana kursu ${row.currency}/${base}: ${fmtSignedCurrency(row.plFx, base)}`
                        : undefined
                    }
                  >
                    {fmtSignedCurrency(row.pl, base)}
                  </div>
                  {row.plPct != null && (
                    <div className={`${s.subValue} mono num`} style={{ color: plColor(row.pl) }}>
                      {fmtSignedPct(row.plPct)}
                    </div>
                  )}
                </td>
                <td>
                  <div className={s.sentCell}>{sentiment(row)}</div>
                </td>
                <td>{deleteButton(row)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Razem ({visible.length})</td>
              <td colSpan={5} />
              <td className="mono num">{fmtCurrency(totals.value, base)}</td>
              <td className="mono num">{totals.weight.toFixed(1)}%</td>
              <td className="mono num" style={{ color: 'var(--muted)' }}>
                {fmtCurrency(totals.cost, base)}
              </td>
              <td className="mono num" style={{ color: plColor(totals.pl) }}>
                {fmtSignedCurrency(totals.pl, base)}
              </td>
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
        {fx && <FxNote date={fx.date} sources={fx.sources} style={{ padding: '8px 16px 12px' }} />}
      </div>

      <div className={s.mobileCards}>
        {visible.map(row => (
          <div key={row.id} className={s.mCard}>
            <div className={s.mCardTop}>
              {identity(row)}
              <div className={s.mCardRight}>
                <div className="mono num" style={{ fontWeight: 700, fontSize: 14 }}>
                  {fmtCurrency(row.value, base)}
                </div>
                <div
                  className="mono num"
                  style={{ fontSize: 11.5, fontWeight: 600, color: plColor(row.change24h) }}
                >
                  {fmtSignedPct(row.change24h)}
                </div>
              </div>
            </div>
            <div className={s.mGrid}>
              <div>
                <span>Cena</span>
                <b className="mono num">{row.price == null ? 'brak' : fmtPriceExact(row.price, row.currency)}</b>
              </div>
              <div>
                <span>Śr. cena</span>
                <b className="mono num">{fmtPriceExact(row.position.avg_buy_price, row.currency)}</b>
              </div>
              <div>
                <span>Koszt</span>
                <b className="mono num">{fmtCurrency(row.cost, base)}</b>
              </div>
              <div>
                <span>Udział</span>
                <b className="mono num">{row.weight == null ? '—' : `${row.weight.toFixed(1)}%`}</b>
              </div>
              <div>
                <span>Wynik</span>
                <b className="mono num" style={{ color: plColor(row.pl) }}>
                  {fmtSignedCurrency(row.pl, base)}
                </b>
              </div>
              <div>
                <span>Sentyment</span>
                <b
                  className="mono num"
                  style={{ color: row.sentiment == null ? 'var(--faint)' : sentColor(row.sentiment) }}
                >
                  {row.sentiment == null
                    ? 'brak'
                    : `${(row.sentiment < 0 ? '−' : '+') + Math.abs(row.sentiment).toFixed(2)} ${sentLabel(row.sentiment).toLowerCase()}`}
                </b>
              </div>
            </div>
            <div className={s.mCardActions}>
              <button type="button" className={s.btnGhost} onClick={() => open(row)}>
                Szczegóły
              </button>
              {deleteButton(row)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
