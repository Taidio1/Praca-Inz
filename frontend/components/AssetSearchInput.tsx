'use client';

import React, { useEffect, useRef, useState } from 'react';

import { searchAssets } from '@/lib/api';
import { MONO } from '@/lib/format';
import { ASSET_TYPE_LABELS } from '@/lib/types';
import type { AssetSearchResult, AssetType } from '@/lib/types';

interface Props {
  value: AssetSearchResult | null;
  onSelect: (a: AssetSearchResult | null) => void;
  autoFocus?: boolean;
  /** Bez własnego tła i ramki, gdy pole siedzi w obramowanym kontenerze. */
  bare?: boolean;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--border)',
  border: '1px solid var(--border-2)',
  borderRadius: 7,
  padding: '8px 11px',
  color: 'var(--fg)',
  fontSize: 12.5,
  outline: 'none',
};

const dropdownStyle: React.CSSProperties = {
  position: 'absolute',
  left: 0,
  right: 0,
  top: 'calc(100% + 6px)',
  zIndex: 80,
  background: 'var(--panel)',
  border: '1px solid var(--border-2)',
  borderRadius: 8,
  boxShadow: '0 12px 28px rgba(0,0,0,.32)',
  overflow: 'hidden',
  maxHeight: 260,
  overflowY: 'auto',
};

const stateRowStyle: React.CSSProperties = {
  padding: '10px 12px',
  fontSize: 12,
  color: 'var(--muted-2)',
};

function badgeStyle(assetType: AssetType): React.CSSProperties {
  const isCrypto = assetType === 'crypto';
  return {
    fontSize: 8.5,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    padding: '2px 5px',
    borderRadius: 4,
    background: isCrypto ? 'var(--accent-soft)' : 'var(--pos-soft)',
    color: isCrypto ? 'var(--accent)' : 'var(--pos)',
    flexShrink: 0,
  };
}

export default function AssetSearchInput({ value, onSelect, autoFocus = false, bare = false }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<AssetSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);

  const rootRef = useRef<HTMLDivElement>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && rootRef.current && !rootRef.current.contains(target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, []);

  useEffect(() => {
    requestSeq.current += 1;
    const requestId = requestSeq.current;
    const trimmed = query.trim();

    if (value) {
      setOpen(false);
      setLoading(false);
      setError(false);
      setResults([]);
      return;
    }

    if (trimmed.length < 2) {
      setOpen(false);
      setLoading(false);
      setError(false);
      setResults([]);
      setHighlighted(-1);
      return;
    }

    setOpen(true);
    setLoading(true);
    setError(false);
    setResults([]);
    setHighlighted(-1);

    const timer = window.setTimeout(() => {
      searchAssets(trimmed)
        .then(rows => {
          if (requestSeq.current !== requestId) return;
          setResults(rows);
          setHighlighted(rows.length > 0 ? 0 : -1);
        })
        .catch(() => {
          if (requestSeq.current !== requestId) return;
          setError(true);
          setResults([]);
          setHighlighted(-1);
        })
        .finally(() => {
          if (requestSeq.current === requestId) setLoading(false);
        });
    }, 300);

    return () => window.clearTimeout(timer);
  }, [query, value]);

  const select = (asset: AssetSearchResult) => {
    onSelect(asset);
    setQuery('');
    setOpen(false);
    setResults([]);
    setHighlighted(-1);
  };

  const clear = () => {
    onSelect(null);
    setQuery('');
    setOpen(false);
    setResults([]);
    setHighlighted(-1);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false);
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!open) setOpen(true);
      setHighlighted(prev => (results.length === 0 ? -1 : Math.min(results.length - 1, prev + 1)));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlighted(prev => (results.length === 0 ? -1 : Math.max(0, prev - 1)));
      return;
    }
    if (event.key === 'Enter' && open && highlighted >= 0 && results[highlighted]) {
      event.preventDefault();
      select(results[highlighted]);
    }
  };

  if (value) {
    return (
      <div ref={rootRef} style={{ width: '100%' }}>
        <div
          style={{
            minHeight: 35,
            background: 'var(--border)',
            border: '1px solid var(--accent-line)',
            borderRadius: 7,
            padding: '6px 7px 6px 10px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span style={{ fontFamily: MONO, fontSize: 12, fontWeight: 600, color: 'var(--fg)' }}>
            {value.ticker}
          </span>
          <span
            style={{
              flex: 1,
              minWidth: 0,
              color: 'var(--fg-3)',
              fontSize: 12,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {value.name}
          </span>
          <span style={badgeStyle(value.asset_type)}>{ASSET_TYPE_LABELS[value.asset_type]}</span>
          <button
            type="button"
            aria-label="Wyczyść wybór aktywa"
            onClick={clear}
            style={{
              width: 22,
              height: 22,
              border: '1px solid var(--border-2)',
              borderRadius: 6,
              background: 'var(--panel-2)',
              color: 'var(--muted)',
              cursor: 'pointer',
              lineHeight: 1,
              fontSize: 15,
            }}
          >
            ×
          </button>
        </div>
      </div>
    );
  }

  const trimmed = query.trim();

  return (
    <div ref={rootRef} style={{ position: 'relative', width: '100%' }}>
      <input
        type="text"
        autoFocus={autoFocus}
        placeholder="Szukaj: nazwa lub ticker, np. bitcoin, NVDA..."
        value={query}
        onChange={event => setQuery(event.target.value)}
        onFocus={() => {
          if (trimmed.length >= 2) setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        style={
          bare
            ? { ...inputStyle, background: 'transparent', border: 'none', padding: '0', fontSize: 15, minHeight: 52 }
            : inputStyle
        }
      />
      {open && trimmed.length >= 2 && (
        <div style={dropdownStyle}>
          {loading && <div style={stateRowStyle}>Szukam...</div>}
          {!loading && error && (
            <div style={{ ...stateRowStyle, color: 'var(--neg)' }}>
              Nie udało się wyszukać — spróbuj ponownie.
            </div>
          )}
          {!loading && !error && results.length === 0 && (
            <div style={stateRowStyle}>Brak wyników dla „{trimmed}”</div>
          )}
          {!loading &&
            !error &&
            results.map((item, index) => (
              <button
                key={`${item.asset_type}:${item.ticker}`}
                type="button"
                onMouseDown={event => {
                  event.preventDefault();
                  select(item);
                }}
                onMouseEnter={() => setHighlighted(index)}
                style={{
                  width: '100%',
                  border: 'none',
                  borderBottom: index === results.length - 1 ? 'none' : '1px solid var(--border)',
                  background: index === highlighted ? 'var(--panel-2)' : 'transparent',
                  color: 'var(--fg)',
                  cursor: 'pointer',
                  padding: '9px 11px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 9,
                  textAlign: 'left',
                  fontFamily: 'inherit',
                }}
              >
                <span
                  style={{
                    width: 54,
                    flexShrink: 0,
                    fontFamily: MONO,
                    fontSize: 12,
                    fontWeight: 600,
                    color: 'var(--fg-2)',
                  }}
                >
                  {item.ticker}
                </span>
                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 12,
                    color: 'var(--fg-3)',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {item.name}
                </span>
                <span style={badgeStyle(item.asset_type)}>{ASSET_TYPE_LABELS[item.asset_type]}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
