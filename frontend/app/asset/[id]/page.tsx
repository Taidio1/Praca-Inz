'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';
import { useApp } from '@/lib/store';
import type { AssetDetail, PortfolioTransaction, PricePoint } from '@/lib/types';
import { ASSET_TYPE_LABELS } from '@/lib/types';
import { formatPrice, formatTime, fmtCurrency, fmtSignedCurrency, sentBadgeStyle, sentColor, sentLabel, MONO } from '@/lib/format';
import { CURRENCIES, fmtFxDate, fmtRate } from '@/lib/currency';
import SentChart from '@/components/charts/SentChart';
import PriceChart, { type PriceRange } from '@/components/charts/PriceChart';

const tileStyle: React.CSSProperties = {
  background: 'var(--bg-inset)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '11px 12px',
};

const tileLabelStyle: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--muted-2)',
  letterSpacing: 0.5,
  marginBottom: 6,
  textTransform: 'uppercase',
};

const tileValueStyle: React.CSSProperties = {
  fontFamily: MONO,
  fontSize: 15,
  fontWeight: 700,
  color: 'var(--fg)',
  lineHeight: 1.2,
  wordBreak: 'break-word',
};

const emptyNote: React.CSSProperties = {
  fontSize: 11.5,
  color: 'var(--muted-2)',
  fontStyle: 'italic',
  lineHeight: 1.5,
};

const inputStyle: React.CSSProperties = {
  background: 'var(--border)',
  border: '1px solid var(--border-2)',
  borderRadius: 7,
  padding: '8px 11px',
  color: 'var(--fg)',
  fontSize: 12.5,
  outline: 'none',
};

const iconBtnStyle: React.CSSProperties = {
  background: 'var(--border)',
  border: '1px solid var(--border-2)',
  borderRadius: 7,
  padding: '5px 7px',
  color: 'var(--muted)',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

const iconBtnDangerStyle: React.CSSProperties = {
  ...iconBtnStyle,
  background: 'var(--neg-soft)',
  border: '1px solid var(--neg-line)',
  color: 'var(--neg)',
};

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

/* Wartości jsonb ze snapshotu (indicators/funding) mają kształt zależny od collectora —
   renderowane generycznie jako pary klucz → wartość. */
function JsonTiles({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => typeof v === 'string' || typeof v === 'number');
  if (entries.length === 0) return <div style={emptyNote}>Brak danych.</div>;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(128px,1fr))', gap: 8 }}>
      {entries.map(([k, v]) => (
        <div key={k} style={tileStyle}>
          <div style={tileLabelStyle}>{k.replace(/_/g, ' ')}</div>
          <div style={tileValueStyle}>{typeof v === 'number' ? v.toLocaleString('pl-PL') : String(v)}</div>
        </div>
      ))}
    </div>
  );
}

export default function AssetDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();

  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { positions, refreshPortfolio, showToast } = useApp();
  const position = positions.find(p => p.asset.id === id) ?? null;
  const [transactions, setTransactions] = useState<PortfolioTransaction[] | null>(null);

  const [priceRange, setPriceRange] = useState<PriceRange>(90);
  const [priceSeries, setPriceSeries] = useState<PricePoint[]>([]);

  const [editingTxId, setEditingTxId] = useState<string | null>(null);
  const [editQty, setEditQty] = useState('');
  const [editPrice, setEditPrice] = useState('');
  const [editCurrency, setEditCurrency] = useState('');
  const [editDate, setEditDate] = useState('');
  const [savingTx, setSavingTx] = useState(false);
  const [deletingTxId, setDeletingTxId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getAsset(id)
      .then(d => {
        if (!cancelled) setDetail(d);
      })
      .catch(e => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Nie udało się pobrać danych aktywa.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    if (!position) {
      setTransactions(null);
      return;
    }
    let cancelled = false;
    api
      .getTransactions(position.id)
      .then(t => {
        if (!cancelled) setTransactions(t);
      })
      .catch(() => {
        if (!cancelled) setTransactions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [position?.id]);

  useEffect(() => {
    if (!detail) return;
    let cancelled = false;
    api
      .getPriceSeries(detail.asset.ticker, detail.asset.asset_type, priceRange)
      .then(pts => {
        if (!cancelled) setPriceSeries(pts);
      })
      .catch(() => {
        if (!cancelled) setPriceSeries([]);
      });
    return () => {
      cancelled = true;
    };
  }, [detail, priceRange]);

  const startEdit = (t: PortfolioTransaction) => {
    setEditingTxId(t.id);
    setEditQty(String(t.quantity));
    setEditPrice(t.price != null ? String(t.price) : '');
    setEditCurrency(t.currency);
    setEditDate(t.purchased_at);
  };

  const cancelEdit = () => setEditingTxId(null);

  const saveEdit = async () => {
    if (!position || !editingTxId) return;
    const qty = parseFloat(editQty.replace(',', '.'));
    if (!qty || qty <= 0) {
      showToast('Ilość musi być większa od zera.');
      return;
    }
    if (!editDate || editDate > todayStr()) {
      showToast('Data nie może być z przyszłości.');
      return;
    }
    let priceVal: number | null = null;
    if (editPrice.trim() !== '') {
      const p = parseFloat(editPrice.replace(',', '.'));
      if (!p || p <= 0) {
        showToast('Cena musi być większa od zera.');
        return;
      }
      priceVal = p;
    }
    setSavingTx(true);
    try {
      await api.updateTransaction(position.id, editingTxId, {
        quantity: qty,
        price: priceVal,
        currency: editCurrency || null,
        purchased_at: editDate,
      });
      const fresh = await api.getTransactions(position.id);
      setTransactions(fresh);
      await refreshPortfolio();
      setEditingTxId(null);
      showToast('Zapisano zmiany transakcji.');
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : 'Nie udało się zapisać zmian.');
    } finally {
      setSavingTx(false);
    }
  };

  const deleteTx = async (txId: string) => {
    if (!position) return;
    setDeletingTxId(txId);
    try {
      const result = await api.deleteTransaction(position.id, txId);
      if (result.position_removed) {
        await refreshPortfolio();
        showToast('Usunięto ostatnią transakcję — pozycja została usunięta.');
        router.push('/portfolio');
        return;
      }
      const fresh = await api.getTransactions(position.id);
      setTransactions(fresh);
      await refreshPortfolio();
      showToast('Usunięto transakcję.');
    } catch (e) {
      showToast(e instanceof ApiError ? e.message : 'Nie udało się usunąć transakcji.');
    } finally {
      setDeletingTxId(null);
    }
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '56px 24px', color: 'var(--muted-2)', fontSize: 13 }}>Ładowanie aktywa…</div>;
  }

  if (error || !detail) {
    return (
      <div style={{ textAlign: 'center', padding: '56px 24px', color: 'var(--muted-2)' }}>
        <p style={{ fontSize: 13.5, color: 'var(--neg)' }}>{error ?? 'Nie znaleziono aktywa.'}</p>
      </div>
    );
  }

  const { asset, snapshot, latest_insights: insights } = detail;
  const latest = insights[0];
  const s = latest?.sentiment_score ?? null;
  const price = snapshot?.price ?? null;
  const change = snapshot?.change_24h ?? null;
  const pos = (change ?? 0) >= 0;
  const indicators = snapshot?.indicators ?? null;
  const funding = asset.asset_type === 'crypto' ? snapshot?.funding ?? null : null;
  const sentPoints = insights.map(i => ({ t: i.created_at, score: i.sentiment_score }));

  // Ceny w walucie notowania aktywa; koszt, wartość i wynik w walucie bazowej użytkownika.
  const quoteCurrency = asset.currency;
  const base = position?.base_currency ?? null;
  const invested = position?.cost_basis ?? null;
  const plVal = position?.profit_loss_value ?? null;
  const plPct = position?.profit_loss_pct ?? null;
  const plPos = (plPct ?? 0) >= 0;

  const totalQty = transactions?.reduce((sum, t) => sum + t.quantity, 0) ?? 0;
  // Suma w walucie notowania: każda transakcja po kursie z dnia zakupu (price_in_quote).
  const totalValue =
    transactions?.reduce((sum, t) => sum + (t.price_in_quote != null ? t.quantity * t.price_in_quote : 0), 0) ?? 0;

  return (
    <>
      {/* Header */}
      <div style={{ padding: 14, borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ background: 'var(--border)', borderRadius: 9, padding: '9px 12px', textAlign: 'center', flexShrink: 0 }}>
          <div style={{ fontFamily: MONO, fontSize: 15, fontWeight: 500, color: 'var(--fg)' }}>{asset.ticker}</div>
          <div style={{ fontSize: 9, color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 }}>
            {ASSET_TYPE_LABELS[asset.asset_type]}
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 17, fontWeight: 700, color: 'var(--fg)', letterSpacing: -0.3 }}>{asset.name}</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 5 }}>
            <span style={{ fontFamily: MONO, fontSize: 19, fontWeight: 700, color: 'var(--fg)' }}>{formatPrice(price, quoteCurrency)}</span>
            {change != null && (
              <span style={{ fontWeight: 600, color: pos ? 'var(--pos)' : 'var(--neg)', fontSize: 14 }}>
                {(pos ? '+' : '') + change.toFixed(2)}%
              </span>
            )}
          </div>
          {snapshot?.captured_at && (
            <div style={{ fontSize: 9.5, color: 'var(--faint)', marginTop: 3 }}>snapshot: {formatTime(snapshot.captured_at)}</div>
          )}
        </div>
        {s != null ? (
          <div style={sentBadgeStyle(s)}>
            <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', opacity: 0.7 }}>Sentyment AI</div>
            <div style={{ fontFamily: MONO, fontSize: 19, fontWeight: 700, marginTop: 3 }}>{(s >= 0 ? '+' : '') + s.toFixed(2)}</div>
            <div style={{ fontSize: 9, fontWeight: 600, marginTop: 2, opacity: 0.8 }}>{sentLabel(s)}</div>
          </div>
        ) : (
          <div style={{ ...tileStyle, textAlign: 'center' }}>
            <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--muted-2)' }}>Sentyment AI</div>
            <div style={{ fontFamily: MONO, fontSize: 17, fontWeight: 700, color: 'var(--faint)', marginTop: 3 }}>—</div>
          </div>
        )}
      </div>

      {/* Podsumowanie pozycji */}
      {position && (
        <div style={{ padding: 14, borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 11 }}>
            Podsumowanie pozycji
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(128px,1fr))', gap: 8 }}>
            <div style={tileStyle}>
              <div style={tileLabelStyle}>Posiadana ilość</div>
              <div style={tileValueStyle}>{position.quantity.toLocaleString('pl-PL')}</div>
            </div>
            <div style={tileStyle}>
              <div style={tileLabelStyle}>Śr. cena nabycia</div>
              <div style={tileValueStyle}>{formatPrice(position.avg_buy_price, quoteCurrency)}</div>
            </div>
            <div style={tileStyle}>
              <div style={tileLabelStyle}>Zainwestowane</div>
              <div style={tileValueStyle}>{fmtCurrency(invested, base)}</div>
            </div>
            <div style={tileStyle}>
              <div style={tileLabelStyle}>Wartość obecna</div>
              <div style={tileValueStyle}>{fmtCurrency(position.current_value, base)}</div>
            </div>
            <div style={tileStyle}>
              <div style={tileLabelStyle}>Zysk / strata</div>
              {plVal != null && plPct != null ? (
                <div style={{ ...tileValueStyle, color: plPos ? 'var(--pos)' : 'var(--neg)' }}>
                  {(plPos ? '+' : '') + fmtCurrency(plVal, base)}
                  <span style={{ fontSize: 11, marginLeft: 5 }}>({(plPos ? '+' : '') + plPct.toFixed(2)}%)</span>
                  {position.profit_loss_price != null &&
                    position.profit_loss_fx != null &&
                    position.currency !== base && (
                      <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--faint)', marginTop: 3 }}>
                        cena {fmtSignedCurrency(position.profit_loss_price, base)} · kurs{' '}
                        {fmtSignedCurrency(position.profit_loss_fx, base)}
                      </div>
                    )}
                </div>
              ) : (
                <div style={{ ...tileValueStyle, color: 'var(--faint)' }}>—</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Wykres ceny */}
      <div style={{ padding: 14, borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 11 }}>
          Wykres ceny — dzienny close
        </div>
        <PriceChart
          currency={quoteCurrency}
          points={priceSeries}
          transactions={transactions ?? []}
          range={priceRange}
          onRangeChange={setPriceRange}
        />
      </div>

      {/* Transakcje */}
      {position && transactions && transactions.length > 0 && (
        <div style={{ padding: '0 14px 14px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted-2)', letterSpacing: 0.5, textTransform: 'uppercase', margin: '14px 0 8px' }}>
            Transakcje
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {transactions.map(t =>
              editingTxId === t.id ? (
                <div key={t.id} style={{ ...tileStyle, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <input
                    type="text"
                    inputMode="decimal"
                    placeholder="Ilość"
                    value={editQty}
                    onChange={e => setEditQty(e.target.value.replace(/[^0-9.,]/g, ''))}
                    style={{ ...inputStyle, width: 90 }}
                  />
                  <input
                    type="date"
                    value={editDate}
                    max={todayStr()}
                    onChange={e => setEditDate(e.target.value)}
                    style={{ ...inputStyle, width: 145, colorScheme: 'dark' }}
                  />
                  <input
                    type="text"
                    inputMode="decimal"
                    placeholder="Cena (opcjonalnie)"
                    value={editPrice}
                    onChange={e => setEditPrice(e.target.value.replace(/[^0-9.,]/g, ''))}
                    style={{ ...inputStyle, width: 130 }}
                  />
                  <select
                    aria-label="Waluta ceny"
                    value={editCurrency}
                    onChange={e => setEditCurrency(e.target.value)}
                    style={{ ...inputStyle, width: 86, colorScheme: 'dark' }}
                  >
                    {CURRENCIES.map(c => (
                      <option key={c.code} value={c.code}>
                        {c.code}
                      </option>
                    ))}
                  </select>
                  <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
                    <button
                      type="button"
                      onClick={() => void saveEdit()}
                      disabled={savingTx}
                      style={{
                        background: 'linear-gradient(135deg,var(--accent),var(--accent-2))',
                        color: 'var(--on-accent)',
                        border: 'none',
                        borderRadius: 7,
                        padding: '6px 12px',
                        fontSize: 11.5,
                        fontWeight: 600,
                        cursor: savingTx ? 'default' : 'pointer',
                        fontFamily: 'inherit',
                        opacity: savingTx ? 0.7 : 1,
                      }}
                    >
                      {savingTx ? 'Zapisywanie…' : 'Zapisz'}
                    </button>
                    <button
                      type="button"
                      onClick={cancelEdit}
                      style={{
                        background: 'var(--border)',
                        border: '1px solid var(--border-2)',
                        color: 'var(--muted)',
                        borderRadius: 7,
                        padding: '6px 11px',
                        fontSize: 11.5,
                        cursor: 'pointer',
                        fontFamily: 'inherit',
                      }}
                    >
                      Anuluj
                    </button>
                  </div>
                </div>
              ) : (
                <div key={t.id} style={{ ...tileStyle, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--fg-3)', minWidth: 82 }}>
                    {new Date(t.purchased_at).toLocaleDateString('pl-PL')}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--fg)' }}>{t.quantity.toLocaleString('pl-PL')} szt.</span>
                  <span style={{ fontSize: 12, color: 'var(--muted-2)' }}>po {formatPrice(t.price, t.currency)}</span>
                  {t.currency !== quoteCurrency && t.price != null && (
                    <span
                      style={{ fontSize: 10.5, color: 'var(--faint)' }}
                      title={`Kurs z ${fmtFxDate(t.fx_rate_date)}`}
                    >
                      1 {t.currency} = {fmtRate(t.fx_rate)} {quoteCurrency}
                    </span>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
                    {t.price != null && (
                      <span style={{ fontFamily: MONO, fontSize: 12, color: 'var(--fg-3)' }}>
                        {formatPrice(t.quantity * t.price, t.currency)}
                      </span>
                    )}
                    <button type="button" onClick={() => startEdit(t)} style={iconBtnStyle}>
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path
                          d="M8.5 1.5l2 2L4 10l-2.5.5.5-2.5 6.5-6.5z"
                          stroke="currentColor"
                          strokeWidth="1.1"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteTx(t.id)}
                      disabled={deletingTxId === t.id}
                      style={{ ...iconBtnDangerStyle, opacity: deletingTxId === t.id ? 0.6 : 1 }}
                    >
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path
                          d="M1.5 2.5h9M4.5 2.5V1.5h3v1M9.5 2.5l-.6 7.5H3.1L2.5 2.5"
                          stroke="currentColor"
                          strokeWidth="1.2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              ),
            )}
          </div>
          <div
            style={{
              ...tileStyle,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: 6,
            }}
          >
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Razem
            </span>
            <span style={{ fontFamily: MONO, fontSize: 12.5, color: 'var(--fg)' }}>
              {totalQty.toLocaleString('pl-PL')} szt. · {fmtCurrency(totalValue, quoteCurrency)}
            </span>
          </div>
        </div>
      )}

      {/* Dane rynkowe (wskaźniki + funding ze snapshotu) */}
      <div style={{ padding: 14, borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 11 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Wskaźniki techniczne — kontekst cenowy
          </div>
          <span
            style={{
              fontSize: 9,
              fontFamily: MONO,
              color: 'var(--faint)',
              background: 'var(--bg-inset)',
              border: '1px solid var(--border)',
              borderRadius: 5,
              padding: '2px 7px',
            }}
          >
            snapshot rynkowy
          </span>
        </div>
        {indicators ? (
          <JsonTiles data={indicators} />
        ) : (
          <div style={emptyNote}>
            Brak danych wskaźnikowych — silnik zbierania danych nie zapisał jeszcze snapshotu dla tego aktywa.
          </div>
        )}

        {asset.asset_type === 'crypto' && (
          <>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8, margin: '14px 0 9px' }}>
              Funding / Open Interest
            </div>
            {funding ? (
              <>
                <JsonTiles data={funding} />
                <div style={{ fontSize: 9, color: 'var(--faint)', marginTop: 7, fontStyle: 'italic' }}>
                  Źródło: Bybit API v5 (tylko-odczyt) · dane kontekstowe, nie sygnał transakcyjny.
                </div>
              </>
            ) : (
              <div style={emptyNote}>Brak danych funding — pojawią się po pierwszym snapshocie z Bybit API.</div>
            )}
          </>
        )}
      </div>

      {/* Sentiment history */}
      <div style={{ padding: 14, borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 11 }}>
          Historia sentymentu AI — ostatnie insighty
        </div>
        <SentChart points={sentPoints} />
      </div>

      {/* Insights timeline */}
      <div style={{ padding: 14 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 13 }}>
          Oś czasu insightów
        </div>
        {insights.length === 0 && (
          <div style={emptyNote}>Brak insightów dla tego aktywa — pojawią się, gdy silnik analityczny przetworzy trafne źródła.</div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {insights.map(di => (
            <div key={di.id} style={{ display: 'flex', gap: 11, paddingBottom: 14 }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                <div
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: '50%',
                    flexShrink: 0,
                    marginTop: 2,
                    background: sentColor(di.sentiment_score),
                    boxShadow: '0 0 0 2px var(--bg)',
                  }}
                />
                <div style={{ flex: 1, width: 1, background: 'var(--border)', marginTop: 4 }} />
              </div>
              <div style={{ flex: 1, paddingBottom: 2 }}>
                <div style={{ fontSize: 10, color: 'var(--muted-2)', marginBottom: 4 }}>{formatTime(di.created_at)}</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-2)', marginBottom: 4, lineHeight: 1.3 }}>{di.title}</div>
                <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>{di.summary}</div>
                {di.price_context && (
                  <div style={{ fontSize: 11, color: 'var(--accent)', fontStyle: 'italic', marginTop: 5 }}>{di.price_context}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
