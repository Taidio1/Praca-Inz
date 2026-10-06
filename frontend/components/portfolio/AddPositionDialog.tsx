'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import CurrencySelect from './CurrencySelect';
import Dialog from './Dialog';
import PopularAssetPicker from './PopularAssetPicker';
import StepProgress from './StepProgress';
import * as api from '@/lib/api';
import { useApp } from '@/lib/store';
import { fmtPriceExact, fmtSignedPct } from '@/lib/format';
import { fmtFxDate, fmtRate, fxSourceLabel } from '@/lib/currency';
import { PHYSICAL_FORM_LABELS, TROY_OUNCE_GRAMS } from '@/lib/types';
import type { AssetSearchResult, AssetType, FxRate, PhysicalForm, PortfolioPosition } from '@/lib/types';
import s from './portfolio.module.css';

const today = () => new Date().toISOString().slice(0, 10);

const toNumber = (raw: string): number | null => {
  const parsed = Number.parseFloat(raw.replace(/\s/g, '').replace(',', '.'));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

const digitsOnly = (raw: string) => raw.replace(/[^0-9.,]/g, '');

const fmtInput = (v: number, maxFrac: number) =>
  v.toLocaleString('pl-PL', { useGrouping: false, maximumFractionDigits: maxFrac });

const ASSET_CLASS: Record<AssetType, { label: string; color: string }> = {
  crypto: { label: 'Kryptowaluty', color: 'var(--accent)' },
  stock: { label: 'Akcje', color: 'var(--pos)' },
  etf: { label: 'Fundusze ETF', color: 'var(--fg-4)' },
  commodity: { label: 'Metale fizyczne', color: 'var(--cat5)' },
};

/** Jednostka ilości fizycznego metalu; w bazie zawsze uncje trojańskie. */
type MetalUnit = 'oz' | 'g';

const OZ_PER_UNIT: Record<MetalUnit, number> = { oz: 1, g: 1 / TROY_OUNCE_GRAMS };

const PHYSICAL_FORMS = Object.keys(PHYSICAL_FORM_LABELS) as PhysicalForm[];

/** Pole, z którego liczone są pozostałe: ilość, wartość albo % portfela. */
type AnchorField = 'quantity' | 'value' | 'pct';

interface Errors {
  asset?: string;
  quantity?: string;
  date?: string;
  price?: string;
}

interface Quote {
  price: number;
  change: number | null;
}

function OField({
  label,
  htmlFor,
  error,
  dashed,
  children,
}: {
  label: React.ReactNode;
  htmlFor?: string;
  error?: string;
  dashed?: boolean;
  children: React.ReactNode;
}) {
  const cls = [s.ofield, dashed ? s.ofieldDashed : '', error ? s.ofieldInvalid : ''].filter(Boolean).join(' ');
  return (
    <div className={s.ofieldWrap}>
      <div className={cls}>
        <label className={s.ofieldLabel} htmlFor={htmlFor}>
          {label}
        </label>
        {children}
      </div>
      {error && <span className={s.fieldError}>{error}</span>}
    </div>
  );
}

export default function AddPositionDialog({
  positions,
  onClose,
  initialAsset = null,
}: {
  positions: PortfolioPosition[];
  onClose: () => void;
  initialAsset?: AssetSearchResult | null;
}) {
  const { addAsset, theme, baseCurrency } = useApp();

  const [asset, setAsset] = useState<AssetSearchResult | null>(initialAsset);
  // Kierunek ostatniego przejścia między krokami; null = dialog dopiero otwarty, bez animacji.
  const [stepDir, setStepDir] = useState<'forward' | 'back' | null>(null);
  const stepRef = useRef<HTMLDivElement>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  // Waluta notowania pochodzi od dostawcy danych (krypto: pary USDT → USD).
  const [fetchedQuoteCurrency, setFetchedQuoteCurrency] = useState<string | null>(null);
  // Waluta transakcji wybrana ręcznie; null = waluta notowania.
  const [txCurrency, setTxCurrency] = useState<string | null>(null);
  // Cena zamknięcia z dnia operacji w walucie notowania (przed przeliczeniem).
  const [autoPrice, setAutoPrice] = useState<{ price: number; date: string } | null>(null);
  const [txFx, setTxFx] = useState<FxRate | null>(null);
  const [txFxFailed, setTxFxFailed] = useState(false);
  const [baseFx, setBaseFx] = useState<FxRate | null>(null);
  const [anchor, setAnchor] = useState<{ field: AnchorField; raw: string }>({ field: 'quantity', raw: '' });
  const [date, setDate] = useState(today);
  const [price, setPrice] = useState('');
  const [priceLoading, setPriceLoading] = useState(false);
  const [priceFetchFailed, setPriceFetchFailed] = useState(false);
  const [priceTouched, setPriceTouched] = useState(false);
  const [priceNonce, setPriceNonce] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [metalUnit, setMetalUnit] = useState<MetalUnit>('oz');
  const [physicalForm, setPhysicalForm] = useState<PhysicalForm>('coin');

  const isMetal = asset?.asset_type === 'commodity';
  // Ile uncji to jedna jednostka wpisana w formularzu; cena i ilość w polach są w tej jednostce.
  const ozPerUnit = isMetal ? OZ_PER_UNIT[metalUnit] : 1;
  const unitLabel = isMetal ? metalUnit : 'szt.';

  const existing = useMemo(
    () =>
      asset
        ? positions.find(
            p =>
              p.asset.ticker.toUpperCase() === asset.ticker.toUpperCase() &&
              p.asset.asset_type === asset.asset_type,
          ) ?? null
        : null,
    [positions, asset],
  );

  // Suma bieżących wartości pozycji — backend liczy je już w walucie bazowej.
  const portfolioTotal = useMemo(
    () => positions.reduce((sum, p) => sum + (p.current_value ?? 0), 0),
    [positions],
  );

  const quoteCurrency =
    existing?.currency ??
    (asset?.asset_type === 'crypto' || asset?.asset_type === 'commodity' ? 'USD' : null) ??
    fetchedQuoteCurrency;
  const currency = txCurrency ?? quoteCurrency;
  const converted = currency != null && quoteCurrency != null && currency !== quoteCurrency;

  // Notowanie w nagłówku: dwa ostatnie dzienne zamknięcia dają cenę i zmianę dzienną.
  useEffect(() => {
    setQuote(null);
    setFetchedQuoteCurrency(null);
    if (!asset) return;
    let cancelled = false;
    api
      .getPriceSeriesFull(asset.ticker, asset.asset_type, 7)
      .then(({ points, currency: seriesCurrency }) => {
        if (cancelled) return;
        if (seriesCurrency) setFetchedQuoteCurrency(seriesCurrency);
        if (points.length === 0) return;
        const last = points[points.length - 1].price;
        const prev = points.length > 1 ? points[points.length - 2].price : null;
        setQuote({ price: last, change: prev ? ((last - prev) / prev) * 100 : null });
      })
      .catch(() => {
        if (!cancelled) setQuote(null);
      });
    return () => {
      cancelled = true;
    };
  }, [asset]);

  // Cena zamknięcia z dnia operacji, w walucie notowania.
  useEffect(() => {
    if (!asset || !date || priceTouched) return;
    let cancelled = false;
    setPriceLoading(true);
    setPriceFetchFailed(false);
    setAutoPrice(null);
    api
      .getPriceOnDate(asset.ticker, asset.asset_type, date)
      .then(p => {
        if (cancelled) return;
        if (p.currency) setFetchedQuoteCurrency(p.currency);
        setAutoPrice({ price: p.price, date });
      })
      .catch(() => {
        if (cancelled) return;
        setPrice('');
        setPriceFetchFailed(true);
      })
      .finally(() => {
        if (!cancelled) setPriceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [asset, date, priceTouched, priceNonce]);

  // Kurs waluty notowania → waluty transakcji z dnia operacji (historyczny, nie dzisiejszy).
  useEffect(() => {
    setTxFx(null);
    setTxFxFailed(false);
    if (!converted || !quoteCurrency || !currency || !date) return;
    let cancelled = false;
    api
      .getFxRate(quoteCurrency, currency, date)
      .then(fx => {
        if (!cancelled) setTxFx(fx);
      })
      .catch(() => {
        if (!cancelled) setTxFxFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [converted, quoteCurrency, currency, date]);

  // Bieżący kurs waluty transakcji → bazowej, do udziału w portfelu.
  useEffect(() => {
    setBaseFx(null);
    if (!currency || currency === baseCurrency) return;
    let cancelled = false;
    api
      .getFxRate(currency, baseCurrency)
      .then(fx => {
        if (!cancelled) setBaseFx(fx);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [currency, baseCurrency]);

  // Automatyczna cena trafia do pola dopiero przeliczona na walutę transakcji
  // (i dla metali na wybraną jednostkę: notowanie jest za uncję).
  useEffect(() => {
    if (priceTouched || !autoPrice || autoPrice.date !== date) return;
    const perUnit = autoPrice.price * ozPerUnit;
    if (!converted) {
      setPrice(fmtInput(perUnit, 8));
      return;
    }
    if (txFx && txFx.requested_date === date) setPrice(fmtInput(perUnit * txFx.rate, 8));
    else setPrice('');
  }, [autoPrice, converted, txFx, date, priceTouched, ozPerUnit]);

  // Zmiana jednostki przelicza wpisane wartości, żeby nie zmieniła się wartość transakcji.
  const changeMetalUnit = (next: MetalUnit) => {
    if (next === metalUnit) return;
    const ratio = OZ_PER_UNIT[next] / OZ_PER_UNIT[metalUnit];
    const typedPrice = toNumber(price);
    if (priceTouched && typedPrice != null) setPrice(fmtInput(typedPrice * ratio, 8));
    const typedQty = toNumber(anchor.raw);
    if (anchor.field === 'quantity' && typedQty != null)
      setAnchor({ field: 'quantity', raw: fmtInput(typedQty / ratio, 8) });
    setMetalUnit(next);
  };

  const toBase = currency === baseCurrency ? 1 : baseFx?.rate ?? null;
  const parsedPrice = toNumber(price);
  const anchorNum = toNumber(anchor.raw);

  let parsedQuantity: number | null = null;
  if (anchor.field === 'quantity') parsedQuantity = anchorNum;
  else if (anchorNum != null && parsedPrice != null) {
    if (anchor.field === 'value') parsedQuantity = anchorNum / parsedPrice;
    else if (portfolioTotal > 0 && toBase != null)
      parsedQuantity = ((anchorNum / 100) * portfolioTotal) / toBase / parsedPrice;
  }
  const transactionValue = parsedQuantity != null && parsedPrice != null ? parsedQuantity * parsedPrice : null;
  const portfolioPct =
    transactionValue != null && portfolioTotal > 0 && toBase != null
      ? ((transactionValue * toBase) / portfolioTotal) * 100
      : null;

  const shown = (field: AnchorField, computed: number | null, maxFrac: number) =>
    anchor.field === field ? anchor.raw : computed != null ? fmtInput(computed, maxFrac) : '';

  const edit = (field: AnchorField) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setAnchor({ field, raw: digitsOnly(e.target.value) });

  const submit = async () => {
    if (submitting) return;
    const next: Errors = {};
    if (!asset) next.asset = 'Wybierz aktywo z listy podpowiedzi.';
    if (parsedQuantity == null) next.quantity = 'Podaj ilość większą od zera.';
    if (!date) next.date = 'Podaj datę zakupu.';
    else if (date > today()) next.date = 'Data zakupu nie może być z przyszłości.';
    if (parsedPrice == null) next.price = 'Podaj cenę większą od zera.';
    setErrors(next);
    if (Object.keys(next).length > 0 || !asset || parsedQuantity == null || parsedPrice == null) return;

    setSubmitting(true);
    try {
      // Backend trzyma metale w uncjach trojańskich i cenie za uncję.
      const added = await addAsset(
        asset.ticker,
        asset.asset_type,
        parsedQuantity * ozPerUnit,
        parsedPrice / ozPerUnit,
        date,
        converted ? currency : null,
        isMetal ? physicalForm : null,
      );
      if (added) onClose();
    } finally {
      setSubmitting(false);
    }
  };

  // Krok 1: wybór instrumentu, krok 2: szczegóły operacji.
  const pickAsset = (picked: AssetSearchResult) => {
    setStepDir('forward');
    setAsset(picked);
  };

  const backToPicker = () => {
    setStepDir('back');
    setAsset(null);
    setTxCurrency(null);
    setAnchor({ field: 'quantity', raw: '' });
    setPrice('');
    setPriceTouched(false);
    setPriceFetchFailed(false);
    setErrors({});
    setMetalUnit('oz');
    setPhysicalForm('coin');
  };

  // Po zmianie kroku poprzedni element z fokusem znika; przenosimy fokus do nowego kroku,
  // żeby Escape i Tab dalej działały w dialogu.
  const hasAsset = asset != null;
  useEffect(() => {
    if (stepDir) stepRef.current?.focus({ preventScroll: true });
  }, [hasAsset, stepDir]);

  const details = asset && (
    <>
      <div className={s.formBody}>
        <OField label="Nazwa instrumentu" error={errors.asset} dashed>
          <div className={s.instrument}>
            <span className={`${s.instrumentBadge} mono`}>{asset.ticker}</span>
            <div className={s.instrumentText}>
              <div className={s.instrumentName}>{asset.name}</div>
              <div className={s.instrumentMeta}>
                {asset.ticker} · {ASSET_CLASS[asset.asset_type].label}
              </div>
            </div>
            {quote && (
              <div className={s.instrumentQuote}>
                <b className="mono num">
                  {fmtPriceExact(quote.price, quoteCurrency)}
                  {isMetal ? ' / oz' : ''}
                </b>
                {quote.change != null && (
                  <span className={quote.change >= 0 ? s.pillUp : s.pillDown}>{fmtSignedPct(quote.change)}</span>
                )}
              </div>
            )}
          </div>
        </OField>

        <OField label="Waluta">
          <CurrencySelect
            value={currency}
            quoteCurrency={quoteCurrency}
            disabled={!asset || !quoteCurrency}
            onChange={code => {
              setTxCurrency(code);
              setPriceTouched(false);
            }}
          />
        </OField>

        <OField label="Data operacji" htmlFor="add-date" error={errors.date}>
          <input
            id="add-date"
            className={s.ofieldInput}
            type="date"
            value={date}
            max={today()}
            style={{ colorScheme: theme }}
            onChange={e => {
              setDate(e.target.value);
              setPriceTouched(false);
            }}
          />
        </OField>

        {isMetal && (
          <div className={s.formGrid}>
            <OField label="Forma">
              <div className={s.seg} role="group" aria-label="Forma fizycznego metalu">
                {PHYSICAL_FORMS.map(f => (
                  <button
                    key={f}
                    type="button"
                    className={s.segBtn}
                    aria-pressed={physicalForm === f}
                    onClick={() => setPhysicalForm(f)}
                  >
                    {PHYSICAL_FORM_LABELS[f]}
                  </button>
                ))}
              </div>
            </OField>
            <OField label="Jednostka">
              <div className={s.seg} role="group" aria-label="Jednostka ilości">
                <button
                  type="button"
                  className={s.segBtn}
                  aria-pressed={metalUnit === 'oz'}
                  onClick={() => changeMetalUnit('oz')}
                >
                  Uncje (oz)
                </button>
                <button
                  type="button"
                  className={s.segBtn}
                  aria-pressed={metalUnit === 'g'}
                  onClick={() => changeMetalUnit('g')}
                >
                  Gramy (g)
                </button>
              </div>
            </OField>
          </div>
        )}

        <hr className={s.formDivider} />

        <div className={s.formGrid}>
          <OField label={isMetal ? `Ilość (${unitLabel})` : 'Ilość'} htmlFor="add-quantity" error={errors.quantity}>
            <input
              id="add-quantity"
              className={s.ofieldInput}
              type="text"
              inputMode="decimal"
              placeholder="0"
              value={shown('quantity', parsedQuantity, 8)}
              onChange={edit('quantity')}
            />
          </OField>

          <OField
            label={
              <span title="Zamknięcie z dnia operacji, pobierane automatycznie. Możesz je poprawić.">Cena ⓘ</span>
            }
            htmlFor="add-price"
            error={
              errors.price ??
              (priceFetchFailed
                ? 'Brak ceny dla tej daty, wpisz ją ręcznie.'
                : txFxFailed
                  ? `Brak kursu ${quoteCurrency}/${currency} dla tej daty.`
                  : undefined)
            }
          >
            <input
              id="add-price"
              className={s.ofieldInput}
              type="text"
              inputMode="decimal"
              placeholder={priceLoading ? 'Pobieranie…' : '0'}
              value={price}
              onChange={e => {
                setPrice(digitsOnly(e.target.value));
                setPriceTouched(true);
              }}
            />
            <span className={s.ofieldSuffix}>
              {currency ?? ''}
              {isMetal ? `/${unitLabel}` : ''}
            </span>
            <button
              type="button"
              className={s.iconBtn}
              aria-label="Pobierz cenę z dnia operacji"
              title="Pobierz cenę z dnia operacji"
              disabled={!asset || priceLoading}
              onClick={() => {
                setPriceTouched(false);
                setPriceNonce(n => n + 1);
              }}
            >
              <svg
                width="17"
                height="17"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                className={priceLoading ? s.spin : undefined}
              >
                <path d="M21 12a9 9 0 0 1-15.5 6.2M3 12a9 9 0 0 1 15.5-6.2" />
                <path d="M21 4v5h-5M3 20v-5h5" />
              </svg>
            </button>
          </OField>

          <OField label="Wartość" htmlFor="add-value">
            <input
              id="add-value"
              className={s.ofieldInput}
              type="text"
              inputMode="decimal"
              placeholder="0,00"
              value={shown('value', transactionValue, 2)}
              onChange={edit('value')}
            />
            <span className={s.ofieldSuffix}>{currency ?? ''}</span>
          </OField>

          <OField label="Zakup za % portfela" htmlFor="add-pct">
            <input
              id="add-pct"
              className={s.ofieldInput}
              type="text"
              inputMode="decimal"
              placeholder="0,00"
              disabled={portfolioTotal <= 0 || toBase == null}
              title={
                portfolioTotal <= 0
                  ? 'Portfel jest pusty, nie ma od czego liczyć udziału.'
                  : toBase == null
                    ? `Brak bieżącego kursu ${currency}/${baseCurrency}.`
                    : `Udział w wartości portfela (${baseCurrency}) po bieżącym kursie.`
              }
              value={shown('pct', portfolioPct, 2)}
              onChange={edit('pct')}
            />
            <span className={s.ofieldSuffix}>%</span>
          </OField>
        </div>

        {converted && txFx && (
          <p className={s.fxNote}>
            Kurs z {fmtFxDate(txFx.rate_date)}
            {txFx.rate_date !== txFx.requested_date ? ' (ostatnia tabela przed datą operacji)' : ''}: 1{' '}
            {txFx.base} = {fmtRate(txFx.rate)} {txFx.quote}
            {fxSourceLabel(txFx.source) ? `, źródło: ${fxSourceLabel(txFx.source)}` : ''}.
            {autoPrice && !priceTouched
              ? ` Cena zamknięcia ${fmtPriceExact(autoPrice.price, quoteCurrency)} przeliczona na ${currency}.`
              : ''}
          </p>
        )}

        {isMetal && (
          <p className={s.fxNote}>
            Wycena według ceny kontraktu COMEX z Yahoo (przybliżenie ceny spot za uncję trojańską, 1 oz ={' '}
            {TROY_OUNCE_GRAMS.toLocaleString('pl-PL', { maximumFractionDigits: 2 })} g). Forma zakupu jest zapisywana
            tylko informacyjnie: premię ponad spot uwzględnia cena zakupu, którą możesz poprawić.
          </p>
        )}

        <OField label="Klasa aktywów">
          <div className={s.currency}>
            <span className={s.classDot} style={{ background: ASSET_CLASS[asset.asset_type].color }} />
            <span className={s.instrumentName} style={{ fontWeight: 500 }}>
              {ASSET_CLASS[asset.asset_type].label}
            </span>
          </div>
        </OField>

        {existing && (
          <p className={s.dialogText} style={{ color: 'var(--accent)', margin: 0 }}>
            Masz już {isMetal ? `${fmtInput(existing.quantity, 4)} oz` : `${existing.quantity} szt.`} {existing.asset.ticker}. Zapiszemy dokupienie i przeliczymy średnią
            cenę nabycia.
          </p>
        )}
      </div>

      <div className={s.formFooter}>
        <button type="button" className={s.btnBack} onClick={backToPicker} disabled={submitting}>
          ← Wstecz
        </button>
        <button
          type="button"
          className={s.btnSubmit}
          onClick={() => void submit()}
          disabled={submitting}
        >
          {submitting ? 'Dodawanie…' : 'Dodaj do portfela'}
        </button>
      </div>
    </>
  );

  const stepAnim = stepDir === 'forward' ? s.stepInForward : stepDir === 'back' ? s.stepInBack : undefined;

  return (
    <Dialog title="Dodaj aktywo" onClose={onClose} labelledBy="add-position-title" variant="form">
      <StepProgress
        steps={['Instrument', 'Szczegóły']}
        current={asset ? 1 : 0}
        onStepClick={i => {
          if (i === 0 && asset) backToPicker();
        }}
      />
      <div className={s.stepViewport}>
        <div key={asset ? 'details' : 'pick'} ref={stepRef} tabIndex={-1} className={stepAnim} style={{ outline: 'none' }}>
          {details ?? <PopularAssetPicker onSelect={pickAsset} />}
        </div>
      </div>
    </Dialog>
  );
}
