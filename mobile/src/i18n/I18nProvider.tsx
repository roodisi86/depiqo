/**
 * Language for the whole app: Dutch by default; else the phone's language when it is French or English;
 * a choice in the profile wins (stored on the device and sent to the server with PATCH /me).
 */
import { getLocales } from 'expo-localization';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { prefs } from '../auth/secureTokenStore';
import { isLang, pickLanguage, type Lang, type Params, type Translator } from './core';
import { setCurrentLang, translatorFor } from './runtime';

interface I18nValue extends Translator {
  setLang(lang: Lang, opts?: { persist?: boolean }): void;
  /** True once the user picked a language in the app (then the server's preference does not override it). */
  chosenByUser: boolean;
  ready: boolean;
}

const I18nContext = createContext<I18nValue | null>(null);

function deviceLanguage(): Lang {
  try {
    return pickLanguage(getLocales().map((l) => l.languageTag));
  } catch {
    return 'nl';
  }
}

export function I18nProvider({ children, onLanguageChanged }: { children: React.ReactNode; onLanguageChanged?: (lang: Lang) => void }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const l = deviceLanguage();
    setCurrentLang(l);
    return l;
  });
  const [chosenByUser, setChosen] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    prefs.get('lang').then((stored) => {
      if (!alive) return;
      if (isLang(stored)) {
        setCurrentLang(stored);
        setLangState(stored);
        setChosen(true);
      }
      setReady(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  const setLang = useCallback(
    (next: Lang, opts?: { persist?: boolean }) => {
      setCurrentLang(next);
      setLangState(next);
      if (opts?.persist) {
        setChosen(true);
        void prefs.set('lang', next);
      }
      onLanguageChanged?.(next);
    },
    [onLanguageChanged],
  );

  const value = useMemo<I18nValue>(() => {
    const tr = translatorFor(lang);
    return { ...tr, setLang, chosenByUser, ready };
  }, [lang, setLang, chosenByUser, ready]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const v = useContext(I18nContext);
  if (!v) throw new Error('useI18n outside I18nProvider');
  return v;
}

export type { Lang, Params };
