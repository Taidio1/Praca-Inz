'use client';

import { useEffect, useState } from 'react';
import * as api from '@/lib/api';
import type { ApiAsset, PricePoint } from '@/lib/types';

/* Serie 30-dniowe zmieniają się raz na dobę i są współdzielone między aktywami,
   więc cache przeżywa remount strony — backend i tak trzyma własny TTL. */
const cache = new Map<string, PricePoint[]>();

const cacheKey = (asset: ApiAsset, days: number) => `${asset.ticker}:${asset.asset_type}:${days}`;

export function useSparklines(assets: ApiAsset[], days = 30): Map<string, PricePoint[]> {
  const [series, setSeries] = useState<Map<string, PricePoint[]>>(new Map());

  useEffect(() => {
    let cancelled = false;

    const cached = new Map<string, PricePoint[]>();
    for (const asset of assets) {
      const hit = cache.get(cacheKey(asset, days));
      if (hit) cached.set(asset.id, hit);
    }
    if (cached.size > 0) {
      setSeries(prev => {
        const next = new Map(prev);
        cached.forEach((points, id) => next.set(id, points));
        return next;
      });
    }

    const missing = assets.filter(asset => !cache.has(cacheKey(asset, days)));
    if (missing.length === 0) return;

    void Promise.all(
      missing.map(async asset => {
        let points: PricePoint[] = [];
        try {
          points = await api.getPriceSeries(asset.ticker, asset.asset_type, days);
        } catch {
          points = [];
        }
        cache.set(cacheKey(asset, days), points);
        return [asset.id, points] as const;
      }),
    ).then(entries => {
      if (cancelled) return;
      setSeries(prev => {
        const next = new Map(prev);
        entries.forEach(([id, points]) => next.set(id, points));
        return next;
      });
    });

    return () => {
      cancelled = true;
    };
  }, [assets, days]);

  return series;
}
