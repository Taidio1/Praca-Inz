'use client';

import React, { useState } from 'react';
import AssetSearchInput from '@/components/AssetSearchInput';
import type { AssetSearchResult } from '@/lib/types';
import s from './portfolio.module.css';

interface Group {
  label: string;
  assets: AssetSearchResult[];
}

interface Category {
  id: string;
  label: string;
  hint: string;
  groups: Group[];
}

const single = (assets: AssetSearchResult[]): Group[] => [{ label: '', assets }];

/** Najczęściej wybierane instrumenty. Własne aktywa wyszukuje się w ostatniej zakładce. */
const CATEGORIES: Category[] = [
  {
    id: 'gold',
    label: 'Złoto i metale',
    hint: 'Fizyczny kruszec (monety, sztabki) wyceniany po cenie spot albo fundusze śledzące jego cenę.',
    groups: [
      {
        label: 'Posiadam fizycznie',
        assets: [
          { ticker: 'XAU', name: 'Złoto (fizyczne)', asset_type: 'commodity' },
          { ticker: 'XAG', name: 'Srebro (fizyczne)', asset_type: 'commodity' },
        ],
      },
      {
        label: 'Fundusze ETF',
        assets: [
          { ticker: 'GLD', name: 'SPDR Gold Shares', asset_type: 'etf' },
          { ticker: 'IAU', name: 'iShares Gold Trust', asset_type: 'etf' },
          { ticker: 'SLV', name: 'iShares Silver Trust', asset_type: 'etf' },
        ],
      },
    ],
  },
  {
    id: 'indices',
    label: 'Indeksy',
    hint: 'ETF-y na szeroki rynek akcji.',
    groups: single([
      { ticker: 'VOO', name: 'Vanguard S&P 500 ETF', asset_type: 'etf' },
      { ticker: 'SPY', name: 'SPDR S&P 500 ETF', asset_type: 'etf' },
      { ticker: 'QQQ', name: 'Invesco QQQ (Nasdaq-100)', asset_type: 'etf' },
      { ticker: 'URTH', name: 'iShares MSCI World ETF', asset_type: 'etf' },
      { ticker: 'VT', name: 'Vanguard Total World Stock ETF', asset_type: 'etf' },
    ]),
  },
  {
    id: 'crypto',
    label: 'Kryptowaluty',
    hint: 'Notowania z Bybit, pary USDT.',
    groups: single([
      { ticker: 'BTC', name: 'Bitcoin', asset_type: 'crypto' },
      { ticker: 'ETH', name: 'Ethereum', asset_type: 'crypto' },
      { ticker: 'SOL', name: 'Solana', asset_type: 'crypto' },
      { ticker: 'XRP', name: 'XRP', asset_type: 'crypto' },
      { ticker: 'BNB', name: 'BNB', asset_type: 'crypto' },
      { ticker: 'DOGE', name: 'Dogecoin', asset_type: 'crypto' },
    ]),
  },
  {
    id: 'stocks',
    label: 'Akcje',
    hint: 'Największe spółki z USA i GPW.',
    groups: single([
      { ticker: 'AAPL', name: 'Apple', asset_type: 'stock' },
      { ticker: 'NVDA', name: 'NVIDIA', asset_type: 'stock' },
      { ticker: 'MSFT', name: 'Microsoft', asset_type: 'stock' },
      { ticker: 'AMZN', name: 'Amazon', asset_type: 'stock' },
      { ticker: 'CDR.WA', name: 'CD Projekt', asset_type: 'stock' },
      { ticker: 'PKO.WA', name: 'PKO Bank Polski', asset_type: 'stock' },
    ]),
  },
];

const CUSTOM = 'custom';

export default function PopularAssetPicker({ onSelect }: { onSelect: (asset: AssetSearchResult) => void }) {
  const [tab, setTab] = useState<string>(CATEGORIES[0].id);
  const category = CATEGORIES.find(c => c.id === tab) ?? null;

  return (
    <div className={s.formBody}>
      <div className={s.pickerTabs} role="tablist" aria-label="Kategorie aktywów">
        {[...CATEGORIES.map(c => ({ id: c.id, label: c.label })), { id: CUSTOM, label: 'Inne (własne)' }].map(t => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? s.pickerTabActive : s.pickerTab}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {category ? (
        <div role="tabpanel">
          <p className={s.pickerHint}>{category.hint}</p>
          {category.groups.map(g => (
            <div key={g.label} className={s.pickerGroup}>
              {g.label && <div className={s.pickerGroupLabel}>{g.label}</div>}
              <div className={s.pickerGrid}>
                {g.assets.map(a => (
                  <button
                    key={`${a.asset_type}:${a.ticker}`}
                    type="button"
                    className={s.pickerTile}
                    onClick={() => onSelect(a)}
                  >
                    <span className={`${s.instrumentBadge} mono`}>{a.ticker}</span>
                    <span className={s.pickerTileName}>{a.name}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div role="tabpanel">
          <p className={s.pickerHint}>Wyszukaj dowolną spółkę, ETF lub kryptowalutę po nazwie albo tickerze.</p>
          <div className={`${s.ofield} ${s.ofieldDashed}`}>
            <label className={s.ofieldLabel} htmlFor="pick-asset">
              Nazwa instrumentu
            </label>
            <div id="pick-asset" className={s.instrumentSearch}>
              <AssetSearchInput value={null} onSelect={a => a && onSelect(a)} autoFocus bare />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
