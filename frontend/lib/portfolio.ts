import type { PortfolioPosition } from './types';

/* Ceny (price) są w walucie notowania pozycji (position.currency); wartości, koszty
   i wyniki (value, cost, pl, dayPl) — w walucie bazowej użytkownika. */
export interface PositionMetrics {
  position: PortfolioPosition;
  id: string;
  currency: string | null;
  price: number | null;
  change24h: number | null;
  value: number | null;
  cost: number | null;
  pl: number | null;
  plPct: number | null;
  plPrice: number | null;
  plFx: number | null;
  dayPl: number | null;
  weight: number | null;
  sentiment: number | null;
}

export interface FxNote {
  date: string; // najnowszy dzień kursu użyty w sumach
  sources: string[];
}

export interface PortfolioMetrics {
  baseCurrency: string | null;
  fx: FxNote | null; // null = wszystkie pozycje w walucie bazowej, bez przeliczeń
  rows: PositionMetrics[];
  priced: PositionMetrics[];
  unpriced: PositionMetrics[];
  totalValue: number;
  totalCost: number;
  totalPl: number | null;
  totalPlPct: number | null;
  totalPlPrice: number | null;
  totalPlFx: number | null;
  dayPl: number | null;
  dayPct: number | null;
  weightedSentiment: number | null;
  topWeight: PositionMetrics | null;
  lastCapturedAt: string | null;
}

/** Wszystkie agregaty liczone wyłącznie z pozycji mających cenę — inaczej udział
 *  procentowy odnosiłby się do innego zbioru niż licznik i cicho zaniżał wynik. */
/* Pozycje bez przeliczonej wartości (brak ceny albo kursu) nie trafiają do sum —
   kwoty w różnych walutach nigdy nie są dodawane bez przeliczenia. */
export function computePortfolioMetrics(positions: PortfolioPosition[]): PortfolioMetrics {
  const rows: PositionMetrics[] = positions.map(position => {
    const price = position.snapshot?.price ?? null;
    const change24h = position.snapshot?.change_24h ?? null;
    const value = position.current_value;
    const cost = position.cost_basis;
    return {
      position,
      id: position.id,
      currency: position.currency,
      price,
      change24h,
      value,
      cost,
      pl: position.profit_loss_value,
      plPct: position.profit_loss_pct,
      plPrice: position.profit_loss_price,
      plFx: position.profit_loss_fx,
      dayPl: value != null && change24h != null ? value - value / (1 + change24h / 100) : null,
      weight: null,
      sentiment: position.latest_sentiment_score,
    };
  });

  const priced = rows.filter(r => r.value != null);
  const unpriced = rows.filter(r => r.value == null);

  const totalValue = priced.reduce((sum, r) => sum + (r.value ?? 0), 0);
  const totalCost = priced.reduce((sum, r) => sum + (r.cost ?? 0), 0);
  const withCost = priced.filter(r => r.cost != null);
  const totalPl = withCost.length > 0 ? withCost.reduce((sum, r) => sum + (r.pl ?? 0), 0) : null;
  const totalPlPct = totalPl != null && totalCost > 0 ? (totalPl / totalCost) * 100 : null;
  const withSplit = withCost.filter(r => r.plPrice != null && r.plFx != null);
  const totalPlPrice = withSplit.length > 0 ? withSplit.reduce((sum, r) => sum + (r.plPrice ?? 0), 0) : null;
  const totalPlFx = withSplit.length > 0 ? withSplit.reduce((sum, r) => sum + (r.plFx ?? 0), 0) : null;

  const withChange = priced.filter(r => r.dayPl != null);
  const dayPl = withChange.length > 0 ? withChange.reduce((sum, r) => sum + (r.dayPl ?? 0), 0) : null;
  const dayBase = withChange.reduce((sum, r) => sum + ((r.value ?? 0) - (r.dayPl ?? 0)), 0);
  const dayPct = dayPl != null && dayBase > 0 ? (dayPl / dayBase) * 100 : null;

  for (const row of priced) {
    row.weight = totalValue > 0 ? ((row.value ?? 0) / totalValue) * 100 : null;
  }

  const rated = priced.filter(r => r.sentiment != null && (r.value ?? 0) > 0);
  const ratedValue = rated.reduce((sum, r) => sum + (r.value ?? 0), 0);
  const weightedSentiment =
    ratedValue > 0
      ? rated.reduce((sum, r) => sum + (r.sentiment ?? 0) * (r.value ?? 0), 0) / ratedValue
      : null;

  const topWeight = priced.reduce<PositionMetrics | null>(
    (best, row) => (best == null || (row.value ?? 0) > (best.value ?? 0) ? row : best),
    null,
  );

  const captured = positions
    .map(p => p.snapshot?.captured_at)
    .filter((c): c is string => Boolean(c))
    .sort();

  const baseCurrency = positions.find(p => p.base_currency)?.base_currency ?? null;
  const converted = priced.filter(
    r => r.position.fx_rate_date && r.position.currency !== r.position.base_currency,
  );
  const fx: FxNote | null =
    converted.length > 0
      ? {
          date: converted.map(r => r.position.fx_rate_date as string).sort()[converted.length - 1],
          sources: Array.from(new Set(converted.map(r => r.position.fx_source ?? ''))).filter(Boolean),
        }
      : null;

  return {
    baseCurrency,
    fx,
    rows,
    priced,
    unpriced,
    totalValue,
    totalCost,
    totalPl,
    totalPlPct,
    totalPlPrice,
    totalPlFx,
    dayPl,
    dayPct,
    weightedSentiment,
    topWeight,
    lastCapturedAt: captured.length > 0 ? captured[captured.length - 1] : null,
  };
}
