/* Waluty obsługiwane w transakcjach — ta sama lista co SUPPORTED_CURRENCIES w backendzie
   (wszystkie są w tabeli A NBP i w kursach referencyjnych EBC). */

import type { BaseCurrency } from './types';

export interface CurrencyInfo {
  code: string;
  name: string;
  symbol: string;
}

export const CURRENCIES: CurrencyInfo[] = [
  { code: 'PLN', name: 'Złoty polski', symbol: 'zł' },
  { code: 'USD', name: 'Dolar amerykański', symbol: '$' },
  { code: 'EUR', name: 'Euro', symbol: '€' },
  { code: 'GBP', name: 'Funt szterling', symbol: '£' },
  { code: 'CHF', name: 'Frank szwajcarski', symbol: 'Fr' },
  { code: 'JPY', name: 'Jen japoński', symbol: '¥' },
  { code: 'CAD', name: 'Dolar kanadyjski', symbol: 'C$' },
  { code: 'AUD', name: 'Dolar australijski', symbol: 'A$' },
  { code: 'SEK', name: 'Korona szwedzka', symbol: 'kr' },
  { code: 'NOK', name: 'Korona norweska', symbol: 'kr' },
  { code: 'DKK', name: 'Korona duńska', symbol: 'kr' },
  { code: 'CZK', name: 'Korona czeska', symbol: 'Kč' },
  { code: 'HUF', name: 'Forint węgierski', symbol: 'Ft' },
];

export const BASE_CURRENCIES: BaseCurrency[] = ['PLN', 'USD', 'EUR'];

export function currencyInfo(code: string): CurrencyInfo {
  return CURRENCIES.find(c => c.code === code) ?? { code, name: code, symbol: code };
}

const FX_SOURCE_LABELS: Record<string, string> = {
  nbp: 'NBP',
  frankfurter: 'EBC (Frankfurter)',
};

export function fxSourceLabel(source: string | null | undefined): string | null {
  if (!source || source === 'identity') return null;
  return FX_SOURCE_LABELS[source] ?? source;
}

/* 2026-10-02 → 2.10.2026 */
export function fmtFxDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('pl-PL');
}

/* Kurs z precyzją jak w tabelach NBP (4 miejsca). */
export function fmtRate(rate: number): string {
  return rate.toLocaleString('pl-PL', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}
