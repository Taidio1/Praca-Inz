export function sentColor(s: number): string {
  return s < -0.15 ? 'var(--neg)' : s > 0.15 ? 'var(--pos)' : 'var(--muted)';
}

export function sentLabel(s: number): string {
  return s < -0.15 ? 'Negatywny' : s > 0.15 ? 'Pozytywny' : 'Neutralny';
}

export function sentBg(s: number): string {
  return s < -0.15 ? 'var(--neg-soft)' : s > 0.15 ? 'var(--pos-soft)' : 'var(--neutral-soft)';
}

export function sentBorder(s: number): string {
  return s < -0.15 ? 'var(--neg-line)' : s > 0.15 ? 'var(--pos-line)' : 'var(--neutral-soft)';
}

export function sentBadgeStyle(s: number): React.CSSProperties {
  return {
    background: sentBg(s),
    border: `1px solid ${sentBorder(s)}`,
    borderRadius: 9,
    padding: '6px 10px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    flexShrink: 0,
    color: sentColor(s),
  };
}

export function sentBarStyle(s: number): React.CSSProperties {
  const color = sentColor(s);
  const pct = Math.abs(s) * 50;
  return s < 0
    ? { position: 'absolute', top: 0, height: '100%', background: color, borderRadius: 2, left: `${50 - pct}%`, width: `${pct}%` }
    : { position: 'absolute', top: 0, height: '100%', background: color, borderRadius: 2, left: '50%', width: `${pct}%` };
}

export function relChipStyle(r: number, threshold: number): React.CSSProperties {
  const pass = r >= threshold;
  return {
    padding: '2px 7px',
    borderRadius: 5,
    display: 'inline-flex',
    alignItems: 'center',
    background: pass ? 'var(--accent-soft)' : 'var(--panel-2)',
    border: `1px solid ${pass ? 'var(--accent-line)' : 'var(--border-2)'}`,
    color: pass ? 'var(--accent)' : 'var(--muted-2)',
    flexShrink: 0,
  };
}

export function formatTime(ts: string): string {
  const d = new Date(ts);
  const m = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
  if (m < 1) return 'przed chwilą';
  if (m < 60) return `${m} min temu`;
  if (m < 1440) return `${Math.floor(m / 60)} godz. temu`;
  return `${Math.floor(m / 1440)} dni temu`;
}

/* Kwoty zawsze z kodem waluty — nigdy nie zakładamy USD. Symbol wąski (zł, $, €, £),
   a gdy waluta go nie ma, Intl pokazuje kod (np. CHF). */
const moneyFormats = new Map<string, Intl.NumberFormat>();

/* Waluty, których wąski symbol jest niejednoznaczny (CAD/AUD → $, SEK/NOK/DKK → kr) — pokazujemy kod. */
const CODE_DISPLAY = new Set(['CAD', 'AUD', 'SEK', 'NOK', 'DKK']);

function display(currency: string): 'code' | 'narrowSymbol' {
  return CODE_DISPLAY.has(currency) ? 'code' : 'narrowSymbol';
}

function moneyFormat(currency: string, digits: number): Intl.NumberFormat {
  const key = `${currency}:${digits}`;
  let f = moneyFormats.get(key);
  if (!f) {
    try {
      f = new Intl.NumberFormat('pl-PL', {
        style: 'currency',
        currency,
        currencyDisplay: display(currency),
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
    } catch {
      // Nieznany kod waluty — liczba z kodem, bez symbolu
      f = new Intl.NumberFormat('pl-PL', { minimumFractionDigits: digits, maximumFractionDigits: digits });
    }
    moneyFormats.set(key, f);
  }
  return f;
}

function withCode(f: Intl.NumberFormat, v: number, currency: string): string {
  const out = f.format(v);
  return f.resolvedOptions().style === 'currency' ? out : `${out} ${currency}`;
}

/* Sumy i wartości: pełne jednostki (12 345 zł). */
export function fmtCurrency(v: number | null | undefined, currency: string | null | undefined): string {
  if (v == null || !currency) return '—';
  return withCode(moneyFormat(currency, 0), Math.round(v), currency);
}

export function fmtSignedCurrency(v: number | null | undefined, currency: string | null | undefined): string {
  if (!currency) return '—';
  return fmtSigned(v, abs => fmtCurrency(abs, currency));
}

/* Ceny bywają ułamkowe (ARB 0,92 $) — liczba miejsc dobierana do rzędu wielkości. */
export function fmtPriceExact(v: number | null | undefined, currency: string | null | undefined): string {
  if (v == null || !currency) return '—';
  const digits = Math.abs(v) < 10 ? 4 : 2;
  return withCode(moneyFormat(currency, digits), v, currency);
}

/* Cena z ostatniego snapshotu rynkowego; null gdy silnik jeszcze nic nie zapisał. */
export function formatPrice(price: number | null | undefined, currency: string | null | undefined): string {
  if (price == null || !currency) return '—';
  return withCode(moneyFormat(currency, 2), price, currency);
}

/* Sam symbol waluty (do sufiksów pól): PLN → zł, USD → $, CHF → CHF. */
export function currencySymbol(currency: string): string {
  try {
    const part = new Intl.NumberFormat('pl-PL', {
      style: 'currency',
      currency,
      currencyDisplay: display(currency),
    })
      .formatToParts(0)
      .find(p => p.type === 'currency');
    return part?.value ?? currency;
  } catch {
    return currency;
  }
}

export function fmtQty(v: number): string {
  const digits = Math.abs(v) < 1 ? 6 : Math.abs(v) < 100 ? 4 : 2;
  return v.toLocaleString('pl-PL', { maximumFractionDigits: digits });
}

/* Znak jawny obok koloru — wynik musi być czytelny bez rozróżniania barw. */
export function fmtSigned(v: number | null | undefined, fmt: (abs: number) => string): string {
  if (v == null) return '—';
  return (v < 0 ? '−' : '+') + fmt(Math.abs(v));
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  return v == null ? '—' : v.toFixed(digits) + '%';
}

export function fmtSignedPct(v: number | null | undefined, digits = 2): string {
  return fmtSigned(v, abs => abs.toFixed(digits) + '%');
}

export function plural(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one;
  const mod10 = n % 10;
  const mod100 = n % 100;
  return mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? few : many;
}

export function trendColor(v: number | null | undefined): string {
  if (v == null || v === 0) return 'var(--muted)';
  return v > 0 ? 'var(--pos)' : 'var(--neg)';
}

export const CAT_COLORS = ['var(--cat1)', 'var(--cat2)', 'var(--cat3)', 'var(--cat4)', 'var(--cat5)', 'var(--cat6)'];

export const MONO = "var(--font-dm-mono), 'DM Mono', monospace";
export const SANS = "var(--font-dm-sans), 'DM Sans', system-ui, sans-serif";
