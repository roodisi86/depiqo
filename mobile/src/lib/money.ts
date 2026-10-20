/**
 * Money and percentage formatting (pure). Mirrors the backend's formatting per language:
 *   nl  € 1.234,56     fr  1 234,56 €     en  €1,234.56
 * Non-breaking spaces keep an amount on one line. Unknown (null) is always an em dash, never 0 and
 * never another amount.
 */
export type Lang = 'nl' | 'fr' | 'en';

export const UNKNOWN = '\u2014'; // —
const NBSP = '\u00A0';
const NNBSP = '\u202F'; // French thousands separator
const MINUS = '\u2212';

export interface MoneyLike {
  cents: number;
  currency: string;
}

function group(n: number, sep: string): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, sep);
}

export function formatCents(cents: number, lang: Lang): string {
  const neg = cents < 0;
  const c = Math.abs(Math.trunc(cents));
  const whole = Math.floor(c / 100);
  const frac = String(c % 100).padStart(2, '0');
  let text: string;
  if (lang === 'en') text = `€${group(whole, ',')}.${frac}`;
  else if (lang === 'fr') text = `${group(whole, NNBSP)},${frac}${NBSP}€`;
  else text = `€${NBSP}${group(whole, '.')},${frac}`;
  return (neg ? MINUS : '') + text;
}

/** Formats money; null, undefined or a non-EUR amount shows as "—". */
export function formatMoney(m: MoneyLike | null | undefined, lang: Lang): string {
  if (!m || m.currency !== 'EUR' || !Number.isFinite(m.cents)) return UNKNOWN;
  return formatCents(m.cents, lang);
}

/** With an explicit sign for movements: +€ 12,00 / \u2212€ 12,00. Zero has no sign. */
export function formatSignedMoney(m: MoneyLike | null | undefined, lang: Lang): string {
  if (!m || m.currency !== 'EUR') return UNKNOWN;
  if (m.cents > 0) return '+' + formatCents(m.cents, lang);
  return formatCents(m.cents, lang);
}

/** Basis points as a percentage: 25 -> "0,25%" (nl), "0,25 %" (fr), "0.25%" (en). */
export function formatBps(bps: number | null | undefined, lang: Lang, decimals = 2): string {
  if (bps === null || bps === undefined || !Number.isFinite(bps)) return UNKNOWN;
  const v = (bps / 100).toFixed(decimals);
  const num = lang === 'en' ? v : v.replace('.', ',');
  return num + (lang === 'fr' ? `${NBSP}%` : '%');
}

/** A number that is already a percentage (result_pct 0.67 -> "0,67%", percent_per_year 0.4425 -> "0,44%"). */
export function formatPercent(pct: number | null | undefined, lang: Lang, decimals = 2): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return UNKNOWN;
  return formatBps(pct * 100, lang, decimals);
}

/**
 * Reads an amount typed by the user into cents. Accepts "25", "25,5", "25.50", "1.234,56",
 * "1,234.56", "€ 1 234,56". Returns null for anything else (letters, more than two decimals, negative).
 */
export function parseAmountToCents(input: string): number | null {
  const s = input.replace(/[€\s\u00A0\u202F]/g, '');
  if (!s || !/^[0-9.,]+$/.test(s)) return null;
  const lastDot = s.lastIndexOf('.');
  const lastComma = s.lastIndexOf(',');
  let intPart = s;
  let fracPart = '';
  if (lastDot >= 0 && lastComma >= 0) {
    // Both separators: the last one is the decimal separator, the other one only groups thousands.
    const dec = Math.max(lastDot, lastComma);
    const decSep = s.charAt(dec);
    const groupSep = decSep === '.' ? ',' : '.';
    const intRaw = s.slice(0, dec);
    if (intRaw.includes(decSep)) return null;
    const grouping = new RegExp(`^\\d{1,3}(?:\\${groupSep}\\d{3})*$`);
    if (!grouping.test(intRaw)) return null;
    intPart = intRaw.split(groupSep).join('');
    fracPart = s.slice(dec + 1);
  } else if (lastDot >= 0 || lastComma >= 0) {
    const sep = lastDot >= 0 ? '.' : ',';
    const parts = s.split(sep);
    const tail = parts[parts.length - 1] ?? '';
    if (parts.length === 2 && tail.length > 0 && tail.length <= 2) {
      intPart = parts[0] ?? '';
      fracPart = tail;
    } else if (parts.slice(1).every((p) => p.length === 3) && (parts[0] ?? '').length > 0) {
      intPart = parts.join(''); // thousands separators only
    } else {
      return null;
    }
  }
  if (!/^\d+$/.test(intPart) || !/^\d{0,2}$/.test(fracPart) || /[.,]/.test(fracPart)) return null;
  const cents = Number(intPart) * 100 + Number(fracPart.padEnd(2, '0') || '0');
  return Number.isSafeInteger(cents) ? cents : null;
}
