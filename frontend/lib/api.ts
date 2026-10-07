/* Cienki klient REST API backendu (FastAPI). Token uwierzytelniający pochodzi
   z bieżącej sesji Supabase — backend weryfikuje go i egzekwuje RLS. */

import { supabase } from './supabase';
import type {
  AssetDetail,
  CompanyOverview,
  CompanySearchHit,
  EngineStatus,
  EvaluationMetrics,
  PeerComparison,
  PopularCompany,
  AssetSearchResult,
  AssetType,
  FeedPage,
  FxRate,
  Insight,
  PortfolioHistory,
  PortfolioPosition,
  PortfolioTransaction,
  PositionCreate,
  PriceOnDate,
  PricePoint,
  SourceItem,
  SourceFunnel,
  SourcePage,
  SourceStatus,
  Trace,
  TransactionUpdate,
  UserSettings,
  UserSettingsUpdate,
} from './types';

const ROOT = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const BASE = `${ROOT}/api/v1`;

export const FEED_POLL_INTERVAL_MS = 45_000;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  const headers: Record<string, string> = {};
  if (init?.body) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, 'network_error', 'Brak połączenia z API — sprawdź, czy backend działa.');
  }

  if (!res.ok) {
    let code = 'http_error';
    let message = `Błąd API (${res.status})`;
    try {
      const body = await res.json();
      if (body?.error?.code) {
        code = body.error.code;
        message = body.error.message;
      } else if (typeof body?.detail === 'string') {
        message = body.detail;
      }
    } catch {
      /* odpowiedź bez JSON-a — zostaje komunikat generyczny */
    }
    throw new ApiError(res.status, code, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export function getFeed(params: {
  assetId?: string;
  sentiment?: 'pos' | 'neg';
  cursor?: string;
  limit?: number;
} = {}): Promise<FeedPage> {
  return request<FeedPage>(
    `/feed${qs({ asset_id: params.assetId, sentiment: params.sentiment, cursor: params.cursor, limit: params.limit })}`,
  );
}

export function getPortfolio(): Promise<PortfolioPosition[]> {
  return request<PortfolioPosition[]>('/portfolio');
}

export function addPosition(payload: PositionCreate): Promise<PortfolioPosition> {
  return request<PortfolioPosition>('/portfolio', { method: 'POST', body: JSON.stringify(payload) });
}

export function removePosition(positionId: string): Promise<void> {
  return request<void>(`/portfolio/${positionId}`, { method: 'DELETE' });
}

export function getPortfolioHistory(days: number): Promise<PortfolioHistory> {
  return request<PortfolioHistory>(`/portfolio/history${qs({ days })}`);
}

export function getTransactions(positionId: string): Promise<PortfolioTransaction[]> {
  return request<PortfolioTransaction[]>(`/portfolio/${positionId}/transactions`);
}

export function updateTransaction(
  positionId: string,
  txId: string,
  payload: TransactionUpdate,
): Promise<PortfolioPosition> {
  return request<PortfolioPosition>(`/portfolio/${positionId}/transactions/${txId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteTransaction(
  positionId: string,
  txId: string,
): Promise<{ position_removed: boolean }> {
  return request<{ position_removed: boolean }>(
    `/portfolio/${positionId}/transactions/${txId}`,
    { method: 'DELETE' },
  );
}

export function getPriceOnDate(
  ticker: string,
  assetType: AssetType,
  date: string,
): Promise<PriceOnDate> {
  return request<PriceOnDate>(
    `/marketdata/price-on-date${qs({ ticker, asset_type: assetType, date })}`,
  );
}

/* Kurs średni: 1 from = rate to na dzień (weekend/święto → ostatnia wcześniejsza tabela). */
export function getFxRate(from: string, to: string, date?: string): Promise<FxRate> {
  return request<FxRate>(`/marketdata/fx-rate${qs({ from, to, date })}`);
}

export function refreshPrices(): Promise<{ refreshed: number }> {
  return request<{ refreshed: number }>('/portfolio/refresh', { method: 'POST' });
}

export function getPriceSeries(
  ticker: string,
  assetType: AssetType,
  days: number,
): Promise<PricePoint[]> {
  return request<{ points: PricePoint[] }>(
    `/marketdata/price-series${qs({ ticker, asset_type: assetType, days })}`,
  ).then(r => r.points);
}

/* Jak getPriceSeries, ale z walutą notowania serii (do nagłówka okna dodawania). */
export function getPriceSeriesFull(
  ticker: string,
  assetType: AssetType,
  days: number,
): Promise<{ points: PricePoint[]; currency: string | null }> {
  return request<{ points: PricePoint[]; currency: string | null }>(
    `/marketdata/price-series${qs({ ticker, asset_type: assetType, days })}`,
  );
}

export function getAsset(assetId: string): Promise<AssetDetail> {
  return request<AssetDetail>(`/assets/${assetId}`);
}

export function searchAssets(q: string): Promise<AssetSearchResult[]> {
  return request<AssetSearchResult[]>(`/assets/search${qs({ q })}`);
}

export function getAssetSources(
  assetId: string,
  params: { minScore?: number; limit?: number } = {},
): Promise<SourceItem[]> {
  return request<SourceItem[]>(
    `/assets/${assetId}/sources${qs({ min_score: params.minScore, limit: params.limit })}`,
  );
}

export function getSources(
  params: { status?: SourceStatus; assetId?: string; cursor?: string; limit?: number } = {},
): Promise<SourcePage> {
  return request<SourcePage>(
    `/sources${qs({ status: params.status, asset_id: params.assetId, cursor: params.cursor, limit: params.limit })}`,
  );
}

export function getSourcesFunnel(hours = 24): Promise<SourceFunnel> {
  return request<SourceFunnel>(`/sources/funnel${qs({ hours })}`);
}

export function getEvaluationMetrics(): Promise<EvaluationMetrics> {
  return request<EvaluationMetrics>('/sources/evaluation');
}

export function saveRelevanceLabel(itemId: string, assetId: string, relevant: boolean): Promise<void> {
  return request<void>(`/sources/${itemId}/labels/${assetId}`, {
    method: 'PUT', body: JSON.stringify({ relevant }),
  });
}

export function getEngineStatus(): Promise<EngineStatus> {
  return request<EngineStatus>('/engine/status');
}

export function getInsightTrace(insightId: string): Promise<Trace> {
  return request<Trace>(`/insights/${insightId}/trace`);
}

export function getSettings(): Promise<UserSettings> {
  return request<UserSettings>('/settings');
}

export function updateSettings(payload: UserSettingsUpdate): Promise<UserSettings> {
  return request<UserSettings>('/settings', { method: 'PUT', body: JSON.stringify(payload) });
}

/* Analiza spółek — dane publiczne SEC EDGAR + notowania; backend cache'uje odpowiedzi źródeł. */
export function getPopularCompanies(): Promise<PopularCompany[]> {
  return request<PopularCompany[]>('/analysis/popular');
}

export function searchCompanies(q: string): Promise<CompanySearchHit[]> {
  return request<CompanySearchHit[]>(`/analysis/search${qs({ q })}`);
}

export function getCompanyOverview(ticker: string): Promise<CompanyOverview> {
  return request<CompanyOverview>(`/analysis/${encodeURIComponent(ticker)}`);
}

export function getCompanyPeers(ticker: string): Promise<PeerComparison> {
  return request<PeerComparison>(`/analysis/${encodeURIComponent(ticker)}/peers`);
}

/* /health żyje poza prefiksem /api/v1 i nie wymaga tokenu. */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${ROOT}/health`, { cache: 'no-store' });
    return res.ok;
  } catch {
    return false;
  }
}

export type { Insight };
