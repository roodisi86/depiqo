/**
 * Dates, times and sizes per language (pure). A date-only value "YYYY-MM-DD" is never shifted by time
 * zones; a timestamp is shown in the phone's local time.
 */
import { UNKNOWN, type Lang } from './money';

const MONTHS_SHORT: Record<Lang, string[]> = {
  nl: ['jan.', 'feb.', 'mrt.', 'apr.', 'mei', 'jun.', 'jul.', 'aug.', 'sep.', 'okt.', 'nov.', 'dec.'],
  fr: ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
};

const MONTHS_LONG: Record<Lang, string[]> = {
  nl: ['januari', 'februari', 'maart', 'april', 'mei', 'juni', 'juli', 'augustus', 'september', 'oktober', 'november', 'december'],
  fr: ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'],
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
};

interface Ymd {
  y: number;
  m: number; // 1..12
  d: number;
}

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

function parseDateOnly(value: string): Ymd | null {
  const m = DATE_ONLY.exec(value);
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return { y, m: mo, d };
}

function ymdText(v: Ymd, lang: Lang, long: boolean): string {
  const name = (long ? MONTHS_LONG : MONTHS_SHORT)[lang][v.m - 1];
  return `${v.d} ${name} ${v.y}`;
}

/** "2026-10-20" or an ISO timestamp -> "20 okt. 2026". */
export function formatDate(value: string | null | undefined, lang: Lang, long = false): string {
  if (!value) return UNKNOWN;
  const only = parseDateOnly(value);
  if (only) return ymdText(only, lang, long);
  const t = Date.parse(value);
  if (!Number.isFinite(t)) return UNKNOWN;
  const d = new Date(t);
  return ymdText({ y: d.getFullYear(), m: d.getMonth() + 1, d: d.getDate() }, lang, long);
}

/** ISO timestamp -> "20 okt. 2026, 14:05" in local time. */
export function formatDateTime(value: string | null | undefined, lang: Lang): string {
  if (!value) return UNKNOWN;
  const t = Date.parse(value);
  if (!Number.isFinite(t)) return formatDate(value, lang);
  const d = new Date(t);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const date = ymdText({ y: d.getFullYear(), m: d.getMonth() + 1, d: d.getDate() }, lang, false);
  return `${date}, ${hh}:${mm}`;
}

/** "2026-10" -> "oktober 2026". */
export function formatPeriod(period: string, lang: Lang): string {
  const m = /^(\d{4})-(\d{2})$/.exec(period);
  if (!m) return period;
  const idx = Number(m[2]) - 1;
  const name = MONTHS_LONG[lang][idx];
  return name ? `${name} ${m[1]}` : period;
}

export function formatBytes(bytes: number, lang: Lang): string {
  if (!Number.isFinite(bytes) || bytes < 0) return UNKNOWN;
  const units = ['B', 'kB', 'MB', 'GB'];
  let v = bytes;
  let i = 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i += 1;
  }
  const text = i === 0 ? String(v) : v.toFixed(1);
  return `${lang === 'en' ? text : text.replace('.', ',')}\u00A0${units[i]}`;
}

/** True for a real calendar date in "YYYY-MM-DD" form (used for the birth date field). */
export function isValidIsoDate(value: string): boolean {
  const v = parseDateOnly(value);
  if (!v) return false;
  const d = new Date(Date.UTC(v.y, v.m - 1, v.d));
  return d.getUTCFullYear() === v.y && d.getUTCMonth() === v.m - 1 && d.getUTCDate() === v.d;
}

/** Turns "31-12-1990" or "31/12/1990" (how people type a date in NL/BE) into "1990-12-31". */
export function normalizeBirthDate(input: string): string | null {
  const s = input.trim();
  if (isValidIsoDate(s)) return s;
  const m = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/.exec(s);
  if (!m) return null;
  const iso = `${m[3]}-${String(m[2]).padStart(2, '0')}-${String(m[1]).padStart(2, '0')}`;
  return isValidIsoDate(iso) ? iso : null;
}
