/**
 * Tiny translation core (pure). Locale files are nested JSON with identical keys in nl, fr and en
 * (scripts/check-i18n.mjs fails the build otherwise). Placeholders look like {name}.
 * Missing key in the current language: Dutch; missing in Dutch too: the key itself.
 */
import type { Lang } from '../lib/money';

export type { Lang };
export const LANGS: readonly Lang[] = ['nl', 'fr', 'en'];
export const DEFAULT_LANG: Lang = 'nl';

export interface Dict {
  [key: string]: string | Dict;
}

export type Params = Record<string, string | number>;

export function flatten(dict: Dict, prefix = '', out: Record<string, string> = {}): Record<string, string> {
  for (const [k, v] of Object.entries(dict)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'string') out[key] = v;
    else flatten(v, key, out);
  }
  return out;
}

export function interpolate(text: string, params?: Params): string {
  if (!params) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in params ? String(params[name]) : whole));
}

export function isLang(v: unknown): v is Lang {
  return v === 'nl' || v === 'fr' || v === 'en';
}

/** First of nl/fr/en among BCP-47 tags like "fr-BE", "en-GB"; Dutch otherwise. */
export function pickLanguage(tags: readonly (string | null | undefined)[]): Lang {
  for (const tag of tags) {
    const two = (tag ?? '').slice(0, 2).toLowerCase();
    if (isLang(two)) return two;
  }
  return DEFAULT_LANG;
}

export interface Translator {
  lang: Lang;
  t(key: string, params?: Params): string;
  has(key: string): boolean;
  /** Translate a backend machine key (status, kind, error code...) with the server's label as fallback. */
  tk(namespace: string, key: string | null | undefined, fallback?: string | null): string;
}

export function createTranslator(dicts: Record<Lang, Record<string, string>>, lang: Lang): Translator {
  const cur = dicts[lang];
  const base = dicts[DEFAULT_LANG];
  const lookup = (key: string): string | undefined => cur[key] ?? base[key];
  return {
    lang,
    t(key, params) {
      const v = lookup(key);
      return v === undefined ? key : interpolate(v, params);
    },
    has(key) {
      return lookup(key) !== undefined;
    },
    tk(namespace, key, fallback) {
      if (key) {
        const v = lookup(`${namespace}.${key}`);
        if (v !== undefined) return v;
      }
      return fallback ?? key ?? '';
    },
  };
}
