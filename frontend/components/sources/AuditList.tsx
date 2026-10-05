'use client';

import React, { useCallback, useEffect, useState } from 'react';
import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';
import { useApp } from '@/lib/store';
import type { RawSourceItem, SourceStatus } from '@/lib/types';
import { formatTime, MONO, relChipStyle } from '@/lib/format';

const PAGE = 30;
const SOURCE_LABEL: Record<string, string> = { rss: 'RSS', finnhub: 'Finnhub', gdelt: 'GDELT' };
const STATUS_LABEL: Record<SourceStatus, string> = {
  all: 'Wszystkie',
  passed: 'Przeszło',
  rejected: 'Odrzucono',
  unmatched: 'Niepasujące',
};

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function chip(active: boolean): React.CSSProperties {
  return {
    padding: '4px 11px',
    borderRadius: 20,
    border: 'none',
    cursor: 'pointer',
    background: active ? 'var(--accent)' : 'var(--panel)',
    color: active ? 'var(--on-accent)' : 'var(--muted)',
    fontSize: 11.5,
    fontWeight: active ? 600 : 400,
    fontFamily: 'inherit',
    flexShrink: 0,
  };
}

/* Audyt filtra: każdy item z oceną per aktywo i powodem (reason), także odrzucone. */
export default function AuditList() {
  const { positions, settingsThreshold } = useApp();
  const [status, setStatus] = useState<SourceStatus>('all');
  const [assetId, setAssetId] = useState<string | null>(null);
  const [items, setItems] = useState<RawSourceItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(
    async (after?: string) => {
      setLoading(true);
      try {
        const page = await api.getSources({ status, assetId: assetId ?? undefined, cursor: after, limit: PAGE });
        setItems(prev => (after ? [...prev, ...page.items] : page.items));
        setCursor(page.next_cursor);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Nie udało się pobrać itemów.');
      } finally {
        setLoading(false);
      }
    },
    [status, assetId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div style={{ borderBottom: '1px solid var(--border)' }}>
      <div style={{ padding: '9px 14px', display: 'flex', gap: 6, overflowX: 'auto', borderBottom: '1px solid var(--border)' }}>
        {(Object.keys(STATUS_LABEL) as SourceStatus[]).map(s => (
          <button key={s} type="button" onClick={() => setStatus(s)} style={chip(status === s)}>
            {STATUS_LABEL[s]}
          </button>
        ))}
        <span style={{ width: 1, background: 'var(--border)', margin: '0 4px', flexShrink: 0 }} />
        <button type="button" onClick={() => setAssetId(null)} style={chip(assetId === null)}>
          Wszystkie aktywa
        </button>
        {positions.map(p => (
          <button key={p.asset.id} type="button" onClick={() => setAssetId(p.asset.id)} style={chip(assetId === p.asset.id)}>
            {p.asset.ticker}
          </button>
        ))}
      </div>

      <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {error && <p style={{ fontSize: 12.5, color: 'var(--neg)' }}>{error}</p>}
        {!loading && !error && items.length === 0 && (
          <p style={{ fontSize: 11.5, color: 'var(--muted-2)', fontStyle: 'italic' }}>
            Brak itemów dla wybranego filtra.
          </p>
        )}
        {items.map(it => {
          const top = it.assessments[0]?.score ?? 0;
          const passed = it.assessments.length > 0 && top >= settingsThreshold;
          const expanded = open === it.item_id;
          return (
            <div
              key={it.item_id}
              style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 10, padding: '9px 12px', opacity: passed || !it.relevance_done ? 1 : 0.7 }}
            >
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <a href={it.url} target="_blank" rel="noreferrer" style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: 'var(--fg-2)', textDecoration: 'none' }}>
                  {it.title}
                </a>
                {it.assessments.length > 0 && (
                  <div style={relChipStyle(top, settingsThreshold)}>
                    <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 500 }}>{top.toFixed(2)}</span>
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 5, fontSize: 10, color: 'var(--muted-2)', flexWrap: 'wrap', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, color: 'var(--accent)' }}>{SOURCE_LABEL[it.source] ?? it.source}</span>
                <span>·</span>
                <span>{it.outlet ?? hostOf(it.url)}</span>
                <span>·</span>
                <span>{formatTime(it.published_at ?? it.fetched_at)}</span>
                <span>·</span>
                {!it.relevance_done && <span style={{ color: 'var(--faint)' }}>czeka na ocenę</span>}
                {it.relevance_done && it.assessments.length === 0 && <span style={{ color: 'var(--faint)' }}>nie dotyczy portfela</span>}
                {it.assessments.map(a => (
                  <button
                    key={a.asset_id}
                    type="button"
                    onClick={() => setOpen(expanded ? null : it.item_id)}
                    style={{ border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 9.5, fontWeight: 700, padding: '1px 6px', borderRadius: 3, background: 'var(--border)', color: a.score >= settingsThreshold ? 'var(--pos)' : 'var(--neg)' }}
                  >
                    {a.ticker} {a.score.toFixed(2)}
                  </button>
                ))}
              </div>
              {expanded && (
                <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {it.assessments.map(a => (
                    <div key={a.asset_id} style={{ fontSize: 11, color: 'var(--muted-2)', lineHeight: 1.45 }}>
                      <span style={{ fontFamily: MONO, color: 'var(--fg-3)' }}>{a.ticker} · {a.method}</span> · {a.reason}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {loading && <div style={{ textAlign: 'center', padding: '14px 0', fontSize: 12, color: 'var(--muted-2)' }}>Ładowanie…</div>}
        {!loading && cursor && (
          <button
            type="button"
            onClick={() => void load(cursor)}
            style={{ width: '100%', marginTop: 4, background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 10, padding: 10, color: 'var(--accent)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}
          >
            Załaduj starsze
          </button>
        )}
      </div>
    </div>
  );
}
