/* Typy odpowiedzi API — odwzorowanie schematów Pydantic z backend/src/schemas/. */

export type AssetType = 'crypto' | 'stock' | 'etf' | 'commodity';

/* Fizyczny metal (commodity): ilość w uncjach trojańskich, cena za uncję. */
export type PhysicalForm = 'coin' | 'bar' | 'other';

export const PHYSICAL_FORM_LABELS: Record<PhysicalForm, string> = {
  coin: 'Monety',
  bar: 'Sztabki',
  other: 'Inna forma',
};

export const TROY_OUNCE_GRAMS = 31.1034768;

/* Jednostka ilości pozycji: metale w uncjach, reszta w sztukach. */
export function qtyUnit(type: AssetType): string {
  return type === 'commodity' ? 'oz' : 'szt.';
}

export interface ApiAsset {
  id: string;
  ticker: string;
  name: string;
  asset_type: AssetType;
  currency: string; // waluta notowania (ISO 4217)
}

export interface AssetSearchResult {
  ticker: string;
  name: string;
  asset_type: AssetType;
}

export interface Snapshot {
  price: number | null;
  change_24h: number | null;
  indicators: Record<string, unknown> | null;
  funding: Record<string, unknown> | null;
  captured_at: string | null;
}

export interface InsightSource {
  title: string;
  source: string;
  url: string;
  relevance: number;
}

export interface Insight {
  id: string;
  asset_id: string;
  asset_ticker: string | null;
  title: string;
  summary: string;
  sentiment_score: number;
  sentiment_label: string;
  price_context: string | null;
  created_at: string;
  key_items: InsightSource[];
  trigger: 'important' | 'batch' | 'daily' | null;
}

export interface FeedPage {
  items: Insight[];
  next_cursor: string | null;
}

export interface AssetDetail {
  asset: ApiAsset;
  snapshot: Snapshot | null;
  latest_insights: Insight[];
}

export interface PortfolioPosition {
  id: string;
  asset: ApiAsset;
  quantity: number;
  currency: string | null; // waluta notowania: cena i średnia cena zakupu
  base_currency: string | null; // waluta bazowa: wartość, koszt, wynik
  avg_buy_price: number | null;
  current_value_quote: number | null;
  current_value: number | null;
  cost_basis: number | null;
  profit_loss_value: number | null;
  profit_loss_pct: number | null;
  profit_loss_price: number | null; // część wyniku ze zmiany ceny
  profit_loss_fx: number | null; // część wyniku ze zmiany kursu
  fx_rate: number | null; // bieżący kurs waluty notowania → bazowej
  fx_rate_date: string | null;
  fx_source: string | null;
  snapshot: Snapshot | null;
  latest_sentiment_score: number | null;
  latest_sentiment_label: string | null;
}

export interface PortfolioHistoryPoint {
  point_date: string; // YYYY-MM-DD
  value: number;
  cost: number;
}

export interface PortfolioHistory {
  points: PortfolioHistoryPoint[];
  skipped_tickers: string[];
  base_currency: string;
  fx_rate_date: string | null;
  fx_sources: string[];
}

export interface PositionCreate {
  ticker: string;
  asset_type: AssetType;
  quantity: number;
  price: number | null;
  currency: string | null; // waluta ceny; null = waluta notowania
  purchased_at: string; // YYYY-MM-DD
  physical_form?: PhysicalForm | null; // tylko commodity
}

export interface PortfolioTransaction {
  id: string;
  quantity: number;
  price: number | null; // w walucie transakcji
  currency: string;
  fx_rate: number; // kurs waluty transakcji → waluty notowania z dnia zakupu
  fx_rate_date: string;
  price_in_quote: number | null;
  physical_form: PhysicalForm | null;
  purchased_at: string; // YYYY-MM-DD
  created_at: string;
}

export interface PriceOnDate {
  price: number;
  price_date: string; // YYYY-MM-DD
  source: string;
  currency: string | null; // waluta notowania
}

export interface FxRate {
  base: string;
  quote: string;
  rate: number; // 1 base = rate quote
  rate_date: string; // dzień publikacji kursu
  requested_date: string;
  source: string;
}

export interface PricePoint {
  price_date: string; // YYYY-MM-DD
  price: number;
}

export interface TransactionUpdate {
  quantity: number;
  price: number | null;
  currency?: string | null;
  purchased_at: string; // YYYY-MM-DD
}

export interface SourceItem {
  item_id: string;
  title: string;
  source: string;
  url: string;
  published_at: string | null;
  score: number;
  method: string;
  reason: string | null;
}

export interface Trace {
  provider: string;
  model: string;
  prompt: string;
  response: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  cost_usd: number;
  created_at: string;
}

export type BaseCurrency = 'PLN' | 'USD' | 'EUR';

export interface UserSettings {
  relevance_threshold: number;
  notifications: Record<string, unknown>;
  base_currency: BaseCurrency;
}

export interface UserSettingsUpdate {
  relevance_threshold?: number;
  notifications?: Record<string, unknown>;
  base_currency?: BaseCurrency;
}

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  crypto: 'krypto',
  stock: 'akcja',
  etf: 'ETF',
  commodity: 'metal',
};

/* ─── Analiza spółek (backend/src/schemas/analysis.py) ─── */

export interface PopularCompany {
  ticker: string;
  name: string;
  group: string;
  group_label: string;
}

export interface CompanySearchHit {
  ticker: string;
  name: string;
}

export type MetricGroup = 'valuation' | 'profitability' | 'cashflow' | 'balance';
export type MetricFmt = 'x' | 'pct' | 'usd';

export interface CompanyMetric {
  key: string;
  label: string;
  group: MetricGroup;
  fmt: MetricFmt;
  better: 'low' | 'high';
  value: number | null;
  avg_5y: number | null;
  history: Record<string, number | null>;
}

export interface CompanyChartEvent {
  d: string; // YYYY-MM-DD
  kind: 'earnings' | 'dividend';
  label: string;
}

export interface CompanyFinancialYear {
  fiscal_year: number;
  period_end: string;
  revenue: number | null;
  gross_profit: number | null;
  operating_income: number | null;
  net_income: number | null;
  ocf: number | null;
  fcf: number | null;
}

export interface CompanyOverview {
  ticker: string;
  name: string;
  cik: number;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  state: string | null;
  fiscal_year_end: string | null;
  description: string | null;
  description_url: string | null;
  logo_url: string | null;
  website: string | null;
  category: string | null; // branża wg Finnhub
  ipo_date: string | null;
  next_earnings: {
    d: string;
    hour: string | null;
    fiscal_quarter: string | null;
    eps_estimate: number | null;
    revenue_estimate: number | null;
  } | null;
  earnings_history: CompanyEarningsRow[];
  dividends: CompanyDividends | null;
  currency: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  last_close_date: string | null;
  market_cap: number | null;
  enterprise_value: number | null;
  shares_outstanding: number | null;
  beta: number | null;
  range_5y_low: number | null;
  range_5y_high: number | null;
  avg_daily_turnover_5y: number | null;
  returns: Record<'1M' | '3M' | 'YTD' | '1Y' | '5Y', number | null>;
  prices: { d: string; close: number }[];
  events: CompanyChartEvent[];
  metrics: CompanyMetric[];
  financials: CompanyFinancialYear[];
  peers: string[];
  peer_group: string | null;
  fundamentals_as_of: string | null;
  last_filing: { form: string; filing_date: string; report_date: string | null } | null;
  warnings: string[];
}

export interface CompanyEarningsRow {
  period: string;
  fiscal_quarter: string | null;
  eps_actual: number | null;
  eps_estimate: number | null;
  surprise_pct: number | null;
  revenue_actual: number | null; // SEC XBRL
}

export interface CompanyDividends {
  dps_ttm: number;
  indicated_annual: number | null;
  yield_ttm: number | null;
  payout_ratio: number | null;
  fcf_coverage: number | null;
  growth_streak: number;
  paying_streak: number;
  cagr: Record<string, number | null>; // "3" | "5" | "10"
  frequency: string | null;
  payments_per_year: number;
  last_amount: number | null;
  last_ex_date: string | null;
  history_from: number;
  years: { year: number; dps: number; yield_pct: number | null; partial: boolean }[];
}

export interface PeerComparison {
  peers: { ticker: string; name: string; metrics: Record<string, number | null> }[];
  medians: Record<string, number | null>;
}

export interface Assessment {
  asset_id: string;
  ticker: string;
  score: number;
  method: string;
  reason: string | null;
  match_score: number | null;
  embedding_score: number | null;
}

export interface RawSourceItem {
  item_id: string;
  source: string;
  url: string;
  title: string;
  snippet: string | null;
  published_at: string | null;
  fetched_at: string;
  duplicate_of: string | null;
  relevance_done: boolean;
  assessments: Assessment[];
  outlet: string | null;
}

export type SourceStatus = 'all' | 'passed' | 'rejected' | 'unmatched';

export interface SourceFunnel {
  hours: number;
  threshold: number;
  fetched: number;
  duplicates: number;
  scored: number;
  candidates: number;
  passed: number;
  rejected: number;
  unmatched: number;
  sent_to_llm: number;
  insights: number;
  cost_usd: number;
}

export interface SourcePage {
  items: RawSourceItem[];
  next_cursor: string | null;
}

export interface EngineCycle {
  started_at: string;
  finished_at: string | null;
  stats: {
    synthesis?: { created: number; waiting: Record<string, string>; budget_exhausted: boolean };
    ingest?: { tracked_assets: number; fetched: number; inserted: number; duplicates: number; per_source: Record<string, number> } };
  errors: Record<string, string>;
}

export interface EngineStatus {
  last_cycle: EngineCycle | null;
  failing_sources: { key: string; last_fetched_at: string | null; consecutive_failures: number; last_error: string | null }[];
  cost_today_usd: number;
  cost_month_usd: number;
  daily_budget_usd: number;
  budget_exhausted: boolean;
}
