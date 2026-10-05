'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import * as api from '@/lib/api';
import { MONO } from '@/lib/format';
import type { PopularCompany } from '@/lib/types';
import CompanyLogo from '@/components/analysis/CompanyLogo';
import CompanySearch from '@/components/analysis/CompanySearch';
import s from '@/components/analysis/analysis.module.css';

export default function AnalysisIndexPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<PopularCompany[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getPopularCompanies()
      .then(setCompanies)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Nie udało się pobrać listy spółek'));
  }, []);

  const groups = useMemo(() => {
    const map = new Map<string, { label: string; items: PopularCompany[] }>();
    for (const c of companies ?? []) {
      if (!map.has(c.group)) map.set(c.group, { label: c.group_label, items: [] });
      map.get(c.group)!.items.push(c);
    }
    return Array.from(map.values());
  }, [companies]);

  return (
    <div className={s.page}>
      <CompanySearch />

      <p className={s.hint} style={{ fontStyle: 'normal' }}>
        Wskaźniki liczone są z raportów 10-K/10-Q (SEC EDGAR, XBRL) i notowań dziennych. Dostępne są spółki
        raportujące do amerykańskiej SEC. Materiał informacyjny — nie stanowi rekomendacji.
      </p>

      {error && <div className={s.warn}>{error}</div>}

      {!companies && !error && (
        <div className={s.cardPad}>
          <div className={s.groupGrid}>
            {Array.from({ length: 12 }, (_, i) => (
              <div key={i} className={s.skeleton} style={{ height: 54 }} />
            ))}
          </div>
        </div>
      )}

      {groups.map(g => (
        <section key={g.label} className={s.cardPad}>
          <div className={s.eyebrow}>{g.label}</div>
          <div className={s.groupGrid}>
            {g.items.map(c => (
              <button
                key={c.ticker}
                type="button"
                className={s.companyTile}
                onClick={() => router.push(`/analysis/${c.ticker}`)}
              >
                <CompanyLogo ticker={c.ticker} />
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: 'block', fontFamily: MONO, fontWeight: 600, fontSize: 12.5 }}>{c.ticker}</span>
                  <span
                    style={{
                      display: 'block',
                      fontSize: 11.5,
                      color: 'var(--muted)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {c.name}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
