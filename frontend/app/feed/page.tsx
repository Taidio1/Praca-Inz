'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useApp } from '@/lib/store';
import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';
import type { Insight } from '@/lib/types';
import { ASSET_TYPE_LABELS } from '@/lib/types';
import { formatTime, relChipStyle, sentBadgeStyle, sentBarStyle, sentLabel, MONO } from '@/lib/format';
import EngineStatusBar from '@/components/sources/EngineStatusBar';

const TRIGGER_LABEL: Record<string, string> = {
  important: 'ważne wydarzenie',
  batch: 'paczka newsów',
  daily: 'podsumowanie dnia',
};

function triggerText(card: Insight): string | null {
  if (!card.trigger) return null;
  if (card.trigger === 'batch') return `paczka ${card.key_items.length} newsów`;
  return TRIGGER_LABEL[card.trigger] ?? card.trigger;
}

const PAGE_SIZE = 20;

function chipStyle(active: boolean): React.CSSProperties {
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

function mergeInsightsById(primary: Insight[], secondary: Insight[]): Insight[] {
  const seen = new Set<string>();
  const merged: Insight[] = [];
  for (const item of [...primary, ...secondary]) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    merged.push(item);
  }
  return merged;
}

export default function FeedPage() {
  const router = useRouter();
  const { positions, settingsThreshold, setFeedConnectionMode } = useApp();
  const [assetFilter, setAssetFilter] = useState<string>('all');
  const [sentFilter, setSentFilter] = useState<'all' | 'pos' | 'neg'>('all');

  const [items, setItems] = useState<Insight[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await api.getFeed({
        assetId: assetFilter === 'all' ? undefined : assetFilter,
        sentiment: sentFilter === 'all' ? undefined : sentFilter,
        limit: PAGE_SIZE,
      });
      setItems(mergeInsightsById(page.items, []));
      setNextCursor(page.next_cursor);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Nie udało się pobrać strumienia informacji.');
    } finally {
      setLoading(false);
    }
  }, [assetFilter, sentFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setFeedConnectionMode('polling');
    return () => setFeedConnectionMode('idle');
  }, [setFeedConnectionMode]);

  useEffect(() => {
    let cancelled = false;

    const pollLatest = async () => {
      try {
        const page = await api.getFeed({
          assetId: assetFilter === 'all' ? undefined : assetFilter,
          sentiment: sentFilter === 'all' ? undefined : sentFilter,
          limit: PAGE_SIZE,
        });
        if (cancelled) return;
        setItems(prev => mergeInsightsById(page.items, prev));
        setNextCursor(prev => prev ?? page.next_cursor);
      } catch {
        /* polling jest dodatkiem live — błąd odświeżenia nie czyści istniejących kart */
      }
    };

    const interval = setInterval(() => void pollLatest(), api.FEED_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [assetFilter, sentFilter]);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.getFeed({
        assetId: assetFilter === 'all' ? undefined : assetFilter,
        sentiment: sentFilter === 'all' ? undefined : sentFilter,
        cursor: nextCursor,
        limit: PAGE_SIZE,
      });
      setItems(prev => mergeInsightsById(prev, page.items));
      setNextCursor(page.next_cursor);
    } catch {
      /* dociąganie nie może wywrócić widoku — istniejące karty zostają */
    } finally {
      setLoadingMore(false);
    }
  };

  const assetTypeById = new Map(positions.map(p => [p.asset.id, p.asset.asset_type]));

  return (
    <>
      <EngineStatusBar showWaiting />

      {/* Filter bar */}
      <div
        style={{
          padding: '10px 14px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          gap: 6,
          flexWrap: 'wrap',
          alignItems: 'center',
          position: 'sticky',
          top: 0,
          background: 'var(--bg)',
          zIndex: 5,
        }}
      >
        <button type="button" onClick={() => setAssetFilter('all')} style={chipStyle(assetFilter === 'all')}>
          Wszystkie
        </button>
        {positions.map(p => (
          <button
            key={p.asset.id}
            type="button"
            onClick={() => setAssetFilter(assetFilter === p.asset.id ? 'all' : p.asset.id)}
            style={chipStyle(assetFilter === p.asset.id)}
          >
            {p.asset.ticker}
          </button>
        ))}
        <button type="button" onClick={() => setSentFilter(sentFilter === 'pos' ? 'all' : 'pos')} style={chipStyle(sentFilter === 'pos')}>
          ↑ Pozytywny
        </button>
        <button type="button" onClick={() => setSentFilter(sentFilter === 'neg' ? 'all' : 'neg')} style={chipStyle(sentFilter === 'neg')}>
          ↓ Negatywny
        </button>
      </div>

      {/* Cards */}
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {loading && <div style={{ textAlign: 'center', padding: '48px 0', fontSize: 13, color: 'var(--muted-2)' }}>Ładowanie strumienia…</div>}

        {error && !loading && (
          <div style={{ textAlign: 'center', padding: '48px 24px' }}>
            <p style={{ fontSize: 13.5, color: 'var(--neg)', marginBottom: 5 }}>{error}</p>
            <p style={{ fontSize: 11, color: 'var(--faint)' }}>Upewnij się, że backend API działa.</p>
          </div>
        )}

        {!loading &&
          !error &&
          items.map(card => {
            const s = card.sentiment_score;
            const assetType = assetTypeById.get(card.asset_id);
            return (
              <article
                key={card.id}
                style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 13, overflow: 'hidden', animation: 'fadeUp .3s ease' }}
              >
                {/* Header */}
                <div style={{ padding: '13px 14px 10px', display: 'flex', gap: 10, alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
                    <div style={{ background: 'var(--border)', borderRadius: 7, padding: '6px 9px', textAlign: 'center', flexShrink: 0 }}>
                      <div style={{ fontFamily: MONO, fontSize: 12, fontWeight: 500, color: 'var(--fg)', lineHeight: 1 }}>
                        {card.asset_ticker ?? '—'}
                      </div>
                      {assetType && (
                        <div style={{ fontSize: 8.5, color: 'var(--faint)', marginTop: 2, letterSpacing: 0.4, textTransform: 'uppercase' }}>
                          {ASSET_TYPE_LABELS[assetType]}
                        </div>
                      )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-2)', lineHeight: 1.35, marginBottom: 2 }}>{card.title}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 10.5, color: 'var(--muted-2)' }}>{formatTime(card.created_at)}</span>
                        {triggerText(card) && (
                          <span
                            style={{
                              fontSize: 9.5,
                              padding: '1px 6px',
                              borderRadius: 3,
                              background: 'var(--border)',
                              color: card.trigger === 'important' ? 'var(--accent)' : 'var(--muted)',
                              fontWeight: card.trigger === 'important' ? 700 : 500,
                            }}
                          >
                            {triggerText(card)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div style={sentBadgeStyle(s)}>
                    <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', opacity: 0.75 }}>{sentLabel(s)}</div>
                    <div style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, lineHeight: 1, marginTop: 2 }}>
                      {(s >= 0 ? '+' : '') + s.toFixed(2)}
                    </div>
                  </div>
                </div>

                {/* Sentiment scale */}
                <div style={{ padding: '0 14px 8px' }}>
                  <div style={{ position: 'relative', height: 3, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={sentBarStyle(s)} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}>
                    <span style={{ fontSize: 8.5, color: 'var(--faint)' }}>↓ Negatywny (−1)</span>
                    <span style={{ fontSize: 8.5, color: 'var(--faint)' }}>(+1) Pozytywny ↑</span>
                  </div>
                </div>

                {/* Summary */}
                <div style={{ padding: '0 14px 10px', fontSize: 12.5, color: 'var(--fg-4)', lineHeight: 1.55 }}>{card.summary}</div>

                {/* Price context */}
                {card.price_context && (
                  <div
                    style={{
                      padding: '7px 14px',
                      background: 'var(--bg-inset)',
                      borderTop: '1px solid var(--border)',
                      borderBottom: '1px solid var(--border)',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 6,
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0, marginTop: 1, color: 'var(--accent)' }}>
                      <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
                      <path d="M6 3.5v2.8l1.4 1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                    </svg>
                    <span style={{ fontSize: 11.5, color: 'var(--accent)', lineHeight: 1.4, fontStyle: 'italic' }}>{card.price_context}</span>
                  </div>
                )}

                {/* Sources */}
                {card.key_items.length > 0 && (
                  <div style={{ padding: '9px 14px' }}>
                    <div style={{ fontSize: 9.5, fontWeight: 700, color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 7 }}>
                      Powiązane źródła
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                      {card.key_items.map((src, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <a
                              href={src.url}
                              target="_blank"
                              rel="noreferrer"
                              style={{
                                fontSize: 11.5,
                                color: 'var(--fg-3)',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                display: 'block',
                                textDecoration: 'none',
                              }}
                            >
                              {src.title}
                            </a>
                            <div style={{ fontSize: 9.5, color: 'var(--muted-2)', marginTop: 1 }}>{src.source}</div>
                          </div>
                          <div style={relChipStyle(src.relevance, settingsThreshold)}>
                            <span style={{ fontFamily: MONO, fontSize: 9.5, fontWeight: 500 }}>{src.relevance.toFixed(2)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Footer */}
                <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    onClick={() => router.push(`/asset/${card.asset_id}`)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--accent)',
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: 0,
                      fontFamily: 'inherit',
                    }}
                  >
                    Szczegóły aktywa
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <path d="M4 2.5l4 3.5-4 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </div>
              </article>
            );
          })}

        {!loading && !error && items.length === 0 && (
          <div style={{ textAlign: 'center', padding: '56px 24px', color: 'var(--muted-2)' }}>
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none" style={{ margin: '0 auto 14px', display: 'block', color: 'var(--faint)' }}>
              <circle cx="20" cy="20" r="17" stroke="currentColor" strokeWidth="1.5" />
              <path d="M14 26l6-11 6 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <p style={{ fontSize: 13.5, color: 'var(--muted-2)', marginBottom: 5 }}>Brak insightów dla wybranych filtrów</p>
            <p style={{ fontSize: 11, color: 'var(--faint)' }}>
              {positions.length === 0
                ? 'Dodaj aktywa do portfela, aby system zaczął zbierać informacje.'
                : 'Insighty pojawią się, gdy dla aktywa zbierze się paczka trafnych newsów. Stan oczekiwania widać nad listą.'}
            </p>
          </div>
        )}

        {!loading && !error && nextCursor && (
          <button
            type="button"
            onClick={() => void loadMore()}
            disabled={loadingMore}
            style={{
              width: '100%',
              background: 'var(--panel)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 12,
              color: 'var(--accent)',
              fontSize: 12.5,
              fontWeight: 600,
              cursor: loadingMore ? 'default' : 'pointer',
              fontFamily: 'inherit',
              opacity: loadingMore ? 0.7 : 1,
            }}
          >
            {loadingMore ? 'Ładowanie…' : 'Załaduj starsze'}
          </button>
        )}
      </div>
    </>
  );
}
