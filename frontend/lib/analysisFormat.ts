/* Formatowanie liczb w widoku analizy spółek (polska notacja: przecinek dziesiętny, mln/mld/bln). */

import type { CompanyMetric, MetricFmt } from './types';

const nf = (digits: number) =>
  new Intl.NumberFormat('pl-PL', { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function fmtNum(v: number | null | undefined, digits = 2): string {
  return v == null || !Number.isFinite(v) ? '—' : nf(digits).format(v);
}

/* 4,91 bln USD — skala dobierana do rzędu wielkości. */
export function fmtBig(v: number | null | undefined, currency = 'USD'): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  const scales: [number, string][] = [
    [1e12, 'bln'],
    [1e9, 'mld'],
    [1e6, 'mln'],
    [1e3, 'tys.'],
  ];
  for (const [base, label] of scales) {
    if (abs >= base) return `${fmtNum(v / base, 2)} ${label} ${currency}`;
  }
  return `${fmtNum(v, 0)} ${currency}`;
}

export function fmtMoney(v: number | null | undefined, currency = 'USD'): string {
  return v == null ? '—' : `${fmtNum(v, 2)} ${currency}`;
}

export function fmtSignedPctPl(v: number | null | undefined, digits = 1): string {
  if (v == null) return '—';
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${fmtNum(Math.abs(v), digits)}%`;
}

export function fmtMetric(v: number | null | undefined, fmt: MetricFmt, currency = 'USD'): string {
  if (v == null) return '—';
  if (fmt === 'pct') return `${fmtNum(v, 1)}%`;
  if (fmt === 'usd') return `${fmtNum(v, 2)} ${currency}`;
  return fmtNum(v, Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2);
}

export type Tone = 'pos' | 'mid' | 'neg' | 'none';

/* Odchylenie względne od punktu odniesienia ze znakiem „korzystności":
   dla mnożników i zadłużenia niżej = korzystniej, dla marż i płynności wyżej. */
export function compareTone(m: CompanyMetric, value: number | null, ref: number | null): Tone {
  if (value == null || ref == null || ref === 0) return 'none';
  const rel = (value - ref) / Math.abs(ref);
  const favourable = m.better === 'high' ? rel : -rel;
  if (favourable > 0.1) return 'pos';
  if (favourable < -0.1) return 'neg';
  return 'mid';
}

export const TONE_COLOR: Record<Tone, string> = {
  pos: 'var(--pos)',
  mid: 'var(--marker)',
  neg: 'var(--neg)',
  none: 'var(--border-2)',
};

/* Wypełnienie paska: 50% = równe punktowi odniesienia; skala logarytmiczna (×4 → pełny pasek). */
export function barFill(value: number | null, ref: number | null): number {
  if (value == null || ref == null || ref === 0) return 0;
  if (Math.sign(value) !== Math.sign(ref)) return value > ref ? 1 : 0.06;
  const ratio = Math.abs(value) / Math.abs(ref);
  const pos = 0.5 + Math.log(ratio) / Math.log(4) / 2;
  return Math.min(1, Math.max(0.06, pos));
}

const LOGO_COLORS = ['var(--cat1)', 'var(--cat2)', 'var(--cat3)', 'var(--cat4)', 'var(--cat5)', 'var(--cat6)'];

export function logoColor(ticker: string): string {
  let h = 0;
  for (const ch of ticker) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return LOGO_COLORS[h % LOGO_COLORS.length];
}

export function fmtDatePl(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(`${iso}T00:00:00`).toLocaleDateString('pl-PL', { day: 'numeric', month: 'short', year: 'numeric' });
}
