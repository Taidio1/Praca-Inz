'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';

import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';
import { useApp } from '@/lib/store';
import {
  fmtBig,
  fmtDatePl,
  fmtMoney,
  fmtNum,
  fmtSignedPctPl,
  TONE_COLOR,
} from '@/lib/analysisFormat';
import type { CompanyMetric, CompanyOverview, MetricGroup, PeerComparison } from '@/lib/types';
import CompanyLogo from '@/components/analysis/CompanyLogo';
import CompanySearch from '@/components/analysis/CompanySearch';
import DividendPanel from '@/components/analysis/DividendPanel';
import EarningsPanel from '@/components/analysis/EarningsPanel';
import FinancialsChart from '@/components/analysis/FinancialsChart';
import MetricCard from '@/components/analysis/MetricCard';
import PriceHistoryChart, { type ChartRange } from '@/components/analysis/PriceHistoryChart';
import AddPositionDialog from '@/components/portfolio/AddPositionDialog';
import s from '@/components/analysis/analysis.module.css';

const GROUPS: { key: MetricGroup; title: string }[] = [
  { key: 'valuation', title: 'Wycena' },
  { key: 'profitability', title: 'Rentowność' },
  { key: 'cashflow', title: 'Przepływy pieniężne' },
  { key: 'balance', title: 'Bilans' },
];

const RANGES: ChartRange[] = ['1M', '3M', 'YTD', '1Y', '5Y'];

const EARNINGS_HOUR: Record<string, string> = { bmo: 'przed sesją', amc: 'po sesji' };

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div title={hint}>
      <div className={s.statLabel}>{label}</div>
      <div className={`${s.statValue} ${s.num}`}>{value}</div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className={s.page}>
      <div className={s.skeleton} style={{ height: 48, borderRadius: 12 }} />
      <div className={s.card} style={{ height: 330, padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className={s.skeleton} style={{ height: 26, width: '40%' }} />
        <div className={s.skeleton} style={{ height: 12, width: '90%' }} />
        <div className={s.skeleton} style={{ height: 12, width: '85%' }} />
        <div className={s.skeleton} style={{ height: 12, width: '70%' }} />
        <div className={s.skeleton} style={{ flex: 1 }} />
      </div>
      <div className={s.metricsGrid}>
        {GROUPS.map(g => (
          <div key={g.key} className={s.skeleton} style={{ height: 240, borderRadius: 14 }} />
        ))}
      </div>
    </div>
  );
}

export default function CompanyAnalysisPage() {
  const params = useParams<{ ticker: string }>();
  const router = useRouter();
  const ticker = decodeURIComponent(params.ticker ?? '').toUpperCase();
  const { positions } = useApp();

  const [data, setData] = useState<CompanyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [peers, setPeers] = useState<PeerComparison | null>(null);
  const [peersLoading, setPeersLoading] = useState(false);
  const [range, setRange] = useState<ChartRange>('5Y');
  const [showEarnings, setShowEarnings] = useState(true);
  const [showDividends, setShowDividends] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    setPeers(null);
    setExpanded(false);
    api
      .getCompanyOverview(ticker)
      .then(o => {
        if (!alive) return;
        setData(o);
        if (o.peers.length > 0) {
          setPeersLoading(true);
          api
            .getCompanyPeers(ticker)
            .then(p => alive && setPeers(p))
            .catch(() => alive && setPeers({ peers: [], medians: {} }))
            .finally(() => alive && setPeersLoading(false));
        }
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setError(
          e instanceof ApiError && e.status === 404
            ? `Nie znaleziono spółki „${ticker}” w rejestrze SEC.`
            : e instanceof Error
              ? e.message
              : 'Nie udało się pobrać danych spółki.',
        );
      });
    return () => {
      alive = false;
    };
  }, [ticker]);

  const byGroup = useMemo(() => {
    const out: Record<MetricGroup, CompanyMetric[]> = { valuation: [], profitability: [], cashflow: [], balance: [] };
    for (const m of data?.metrics ?? []) out[m.group].push(m);
    return out;
  }, [data]);

  const owned = positions.find(p => p.asset.asset_type !== 'crypto' && p.asset.ticker.toUpperCase() === ticker);

  if (error) {
    return (
      <div className={s.page}>
        <CompanySearch />
        <div className={s.warn}>{error}</div>
      </div>
    );
  }
  if (!data) return <Skeleton />;

  const cur = data.currency;
  const changeColor = data.change == null || data.change === 0 ? 'var(--muted)' : data.change > 0 ? 'var(--pos)' : 'var(--neg)';
  const filing = data.last_filing;

  return (
    <div className={s.page}>
      <CompanySearch placeholder={`${data.name} (${data.ticker}) — wyszukaj inną spółkę…`} />

      {data.warnings.map(w => (
        <div key={w} className={s.warn}>
          {w}
        </div>
      ))}

      {/* ═══ Profil + cena ═══ */}
      <section className={`${s.card} ${s.hero}`}>
        <div className={s.heroMain}>
          <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <CompanyLogo ticker={data.ticker} large logoUrl={data.logo_url} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <h2 style={{ fontSize: 21, fontWeight: 700, letterSpacing: -0.4 }}>{data.name}</h2>
                {owned ? (
                  <button type="button" className={s.ghostBtn} onClick={() => router.push(`/asset/${owned.asset.id}`)}>
                    W portfelu →
                  </button>
                ) : (
                  <button type="button" className={s.ghostBtn} onClick={() => setAdding(true)} title="Dodaj spółkę do śledzonego portfela">
                    + Do portfela
                  </button>
                )}
              </div>
              <div className={s.tags}>
                <span className={s.tagStrong}>{data.ticker}</span>
                {data.exchange && <span className={s.tag}>{data.exchange}</span>}
                <span className={s.tag}>US</span>
                {data.sector && <span className={s.tag}>{data.sector}</span>}
                {data.category && data.category !== data.sector && <span className={s.tag}>{data.category}</span>}
                {data.industry && <span className={s.tag}>{data.industry}</span>}
              </div>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 8, fontSize: 11.5, color: 'var(--muted)' }}>
                {data.fiscal_year_end && (
                  <span>
                    Koniec roku obrotowego: <b style={{ color: 'var(--fg-3)' }}>{data.fiscal_year_end.slice(2)}.{data.fiscal_year_end.slice(0, 2)}</b>
                  </span>
                )}
                {data.ipo_date && (
                  <span>
                    IPO: <b style={{ color: 'var(--fg-3)' }}>{fmtDatePl(data.ipo_date)}</b>
                  </span>
                )}
                {data.website && (
                  <a href={data.website} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)', textDecoration: 'none' }}>
                    {data.website.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')} ↗
                  </a>
                )}
                {filing && data.next_earnings && (
                  <span title={filing.report_date ? `Okres sprawozdawczy do ${filing.report_date}` : undefined}>
                    Ostatni raport: <b style={{ color: 'var(--fg-3)' }}>{filing.form} · {fmtDatePl(filing.filing_date)}</b>
                  </span>
                )}
                {data.shares_outstanding != null && (
                  <span>
                    Akcje: <b style={{ color: 'var(--fg-3)' }}>{fmtNum(data.shares_outstanding / 1e9, 2)} mld</b>
                  </span>
                )}
                <a
                  href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${data.cik}&type=10-&dateb=&owner=include&count=40`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: 'var(--accent)', textDecoration: 'none' }}
                >
                  Raporty w SEC EDGAR ↗
                </a>
              </div>
            </div>
          </div>

          {data.description ? (
            <div>
              <p className={`${s.description} ${expanded ? '' : s.clamp}`}>{data.description}</p>
              <div style={{ display: 'flex', gap: 12, marginTop: 6, alignItems: 'center' }}>
                <button type="button" className={s.linkBtn} onClick={() => setExpanded(v => !v)}>
                  {expanded ? 'Zwiń' : 'Czytaj więcej'}
                </button>
                {data.description_url && (
                  <a href={data.description_url} target="_blank" rel="noreferrer" className={s.hint} style={{ fontStyle: 'normal' }}>
                    Źródło: Wikipedia ↗
                  </a>
                )}
              </div>
            </div>
          ) : (
            <p className={s.hint}>Brak opisu spółki w dostępnych źródłach.</p>
          )}

          <div className={s.statsRow}>
            <Stat label="Kapitalizacja" value={fmtBig(data.market_cap, cur)} hint="Cena × liczba akcji w obrocie (z ostatniego raportu)" />
            <Stat label="Beta" value={fmtNum(data.beta, 2)} hint="Beta 5Y względem S&P 500 (SPY), tygodniowe stopy zwrotu" />
            <Stat
              label="Zakres cenowy 5Y"
              value={`${fmtNum(data.range_5y_low, 2)} – ${fmtNum(data.range_5y_high, 2)} ${cur}`}
            />
            <Stat label="Śr. dzienny obrót 5Y" value={fmtBig(data.avg_daily_turnover_5y, cur)} hint="Średnia z (cena zamknięcia × wolumen)" />
            {data.next_earnings ? (
              <Stat
                label="Następne wyniki"
                value={fmtDatePl(data.next_earnings.d)}
                hint={[
                  data.next_earnings.fiscal_quarter && `Kwartał fiskalny ${data.next_earnings.fiscal_quarter}`,
                  EARNINGS_HOUR[data.next_earnings.hour ?? ''],
                  'Źródło: kalendarz wyników Finnhub',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              />
            ) : (
              <Stat
                label="Ostatni raport"
                value={filing ? `${filing.form} · ${fmtDatePl(filing.filing_date)}` : '—'}
                hint={filing?.report_date ? `Okres sprawozdawczy do ${filing.report_date}` : undefined}
              />
            )}
          </div>
        </div>

        <div className={s.heroSide}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                <span className={s.num} style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.6 }}>
                  {fmtMoney(data.price, cur)}
                </span>
                <span className={s.num} style={{ fontSize: 12.5, color: changeColor, fontWeight: 600 }}>
                  {data.change != null ? `${data.change > 0 ? '+' : data.change < 0 ? '−' : ''}${fmtNum(Math.abs(data.change), 3)} ${cur}` : ''}{' '}
                  ({fmtSignedPctPl(data.change_pct, 1)})
                </span>
              </div>
              <div className={s.hint} style={{ fontStyle: 'normal', marginTop: 2 }}>
                Ostatnie notowanie: {fmtDatePl(data.last_close_date)}
              </div>
            </div>
            <div className={s.chips}>
              <button type="button" className={showEarnings ? s.chipOn : s.chip} onClick={() => setShowEarnings(v => !v)} aria-pressed={showEarnings}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--marker)' }} /> Wyniki
              </button>
              <button type="button" className={showDividends ? s.chipOn : s.chip} onClick={() => setShowDividends(v => !v)} aria-pressed={showDividends}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)' }} /> Dywidendy
              </button>
            </div>
          </div>

          <PriceHistoryChart
            prices={data.prices}
            events={data.events}
            range={range}
            showEarnings={showEarnings}
            showDividends={showDividends}
            currency={cur}
          />

          <div className={s.returns} role="group" aria-label="Zakres wykresu">
            {RANGES.map(r => {
              const v = data.returns[r];
              return (
                <button key={r} type="button" className={r === range ? s.returnCellOn : s.returnCell} onClick={() => setRange(r)} aria-pressed={r === range}>
                  <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600 }}>{r}</div>
                  <div className={s.num} style={{ fontSize: 12.5, fontWeight: 700, color: v == null ? 'var(--muted)' : v >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    {fmtSignedPctPl(v, 1)}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* ═══ Spółki porównawcze ═══ */}
      <section className={`${s.card} ${s.peersBar}`}>
        <span style={{ fontSize: 12, fontWeight: 700 }}>Spółki porównawcze:</span>
        {data.peers.length === 0 ? (
          <span className={s.hint}>Brak zdefiniowanej grupy porównawczej dla tej spółki — kolumna „vs peers” jest pusta.</span>
        ) : (
          <>
            {data.peers.map(p => (
              <button key={p} type="button" className={s.peerChip} onClick={() => router.push(`/analysis/${p}`)}>
                {p}
              </button>
            ))}
            {data.peer_group && <span className={s.hint}>({data.peer_group})</span>}
          </>
        )}
      </section>

      {/* ═══ Wskaźniki ═══ */}
      <div className={s.metricsGrid}>
        {GROUPS.map(g => (
          <MetricCard
            key={g.key}
            title={g.title}
            metrics={byGroup[g.key]}
            peerMedians={peers?.medians ?? null}
            peersLoading={peersLoading}
            hasPeers={data.peers.length > 0}
            currency={cur}
          />
        ))}
      </div>

      <div className={s.legend}>
        <span>
          <span className={s.legendDot} style={{ background: TONE_COLOR.pos }} />
          korzystniej niż punkt odniesienia (&gt;10%)
        </span>
        <span>
          <span className={s.legendDot} style={{ background: TONE_COLOR.mid }} />w granicach ±10%
        </span>
        <span>
          <span className={s.legendDot} style={{ background: TONE_COLOR.neg }} />
          mniej korzystnie (&gt;10%)
        </span>
        <span>Środek paska = wartość równa średniej 5Y / medianie peers. Dla mnożników i zadłużenia niżej = korzystniej.</span>
      </div>

      {/* ═══ Finanse roczne ═══ */}
      <FinancialsChart financials={data.financials} ticker={data.ticker} currency={cur} />

      {/* ═══ Dywidendy + kalendarz wyników ═══ */}
      <div className={s.twoCol}>
        <DividendPanel dividends={data.dividends} currency={cur} />
        <EarningsPanel data={data} />
      </div>

      <p className={s.hint}>
        Dane finansowe: SEC EDGAR (XBRL, US-GAAP), stan na {fmtDatePl(data.fundamentals_as_of)}; wskaźniki TTM = ostatnie 4
        kwartały. Notowania: Yahoo Finance (dzienne zamknięcia, skorygowane o splity).
        {data.logo_url || data.next_earnings ? ' Logo, strona WWW i terminy wyników: Finnhub.' : ''} Materiał informacyjny i
        edukacyjny — nie stanowi porady inwestycyjnej.
      </p>

      {adding && (
        <AddPositionDialog
          positions={positions}
          onClose={() => setAdding(false)}
          initialAsset={{ ticker: data.ticker, name: data.name, asset_type: 'stock' }}
        />
      )}
    </div>
  );
}
