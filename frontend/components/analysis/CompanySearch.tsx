'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

import { searchCompanies } from '@/lib/api';
import { MONO } from '@/lib/format';
import type { CompanySearchHit } from '@/lib/types';
import s from './analysis.module.css';

/* Wyszukiwarka spółek z rejestru SEC — wybór przenosi na /analysis/[ticker]. */
export default function CompanySearch({ placeholder, initial = '' }: { placeholder?: string; initial?: string }) {
  const router = useRouter();
  const [query, setQuery] = useState(initial);
  const [results, setResults] = useState<CompanySearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (e.target instanceof Node && rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  useEffect(() => {
    const id = ++seq.current;
    const q = query.trim();
    if (q.length < 1 || q === initial) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(false);
    const timer = window.setTimeout(() => {
      searchCompanies(q)
        .then(rows => {
          if (seq.current !== id) return;
          setResults(rows);
          setActive(0);
        })
        .catch(() => {
          if (seq.current === id) setError(true);
        })
        .finally(() => {
          if (seq.current === id) setLoading(false);
        });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, initial]);

  const go = (hit: CompanySearchHit) => {
    setOpen(false);
    setQuery('');
    router.push(`/analysis/${encodeURIComponent(hit.ticker)}`);
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') setOpen(false);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(a => Math.min(results.length - 1, a + 1));
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(a => Math.max(0, a - 1));
    }
    if (e.key === 'Enter' && results[active]) {
      e.preventDefault();
      go(results[active]);
    }
  };

  const q = query.trim();

  return (
    <div ref={rootRef} className={s.searchWrap}>
      <div className={s.searchBox}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="7" cy="7" r="5" stroke="var(--muted)" strokeWidth="1.6" />
          <path d="M11 11l3.5 3.5" stroke="var(--muted)" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <input
          className={s.searchInput}
          value={query}
          placeholder={placeholder ?? 'Szukaj spółki: nazwa lub ticker, np. Apple, MSFT…'}
          onChange={e => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
          aria-label="Szukaj spółki"
        />
      </div>
      {open && q.length >= 1 && q !== initial && (
        <div className={s.dropdown} role="listbox">
          {loading && <div className={s.dropState}>Szukam…</div>}
          {!loading && error && <div className={s.dropState} style={{ color: 'var(--neg)' }}>Nie udało się wyszukać — spróbuj ponownie.</div>}
          {!loading && !error && results.length === 0 && <div className={s.dropState}>Brak spółek dla „{q}”</div>}
          {!loading &&
            !error &&
            results.map((hit, i) => (
              <button
                key={hit.ticker}
                type="button"
                className={i === active ? s.dropItemActive : s.dropItem}
                onMouseDown={e => {
                  e.preventDefault();
                  go(hit);
                }}
                onMouseEnter={() => setActive(i)}
              >
                <span style={{ fontFamily: MONO, fontWeight: 600, width: 64, flexShrink: 0 }}>{hit.ticker}</span>
                <span style={{ color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{hit.name}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
