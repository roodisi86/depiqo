/** Locale dictionaries and the current language (module state, read by the API client for Accept-Language). */
import { createTranslator, DEFAULT_LANG, flatten, type Dict, type Lang, type Translator } from './core';
import en from './locales/en.json';
import fr from './locales/fr.json';
import nl from './locales/nl.json';

export const DICTS: Record<Lang, Record<string, string>> = {
  nl: flatten(nl as unknown as Dict),
  fr: flatten(fr as unknown as Dict),
  en: flatten(en as unknown as Dict),
};

let current: Lang = DEFAULT_LANG;
const translators = new Map<Lang, Translator>();

export function getCurrentLang(): Lang {
  return current;
}

export function setCurrentLang(lang: Lang): void {
  current = lang;
}

export function translatorFor(lang: Lang): Translator {
  let tr = translators.get(lang);
  if (!tr) {
    tr = createTranslator(DICTS, lang);
    translators.set(lang, tr);
  }
  return tr;
}
