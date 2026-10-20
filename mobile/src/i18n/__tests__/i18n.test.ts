/** Same keys and placeholders in nl, fr and en; every backend machine key translated. */
import { createTranslator, flatten, interpolate, pickLanguage, type Dict } from '../core';
import en from '../locales/en.json';
import fr from '../locales/fr.json';
import nl from '../locales/nl.json';
import { MACHINE_KEYS } from '../machineKeys';

const dicts = {
  nl: flatten(nl as unknown as Dict),
  fr: flatten(fr as unknown as Dict),
  en: flatten(en as unknown as Dict),
};

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe('locale files', () => {
  it('have identical keys', () => {
    const base = Object.keys(dicts.nl).sort();
    expect(Object.keys(dicts.fr).sort()).toEqual(base);
    expect(Object.keys(dicts.en).sort()).toEqual(base);
  });

  it('have the same placeholders and no empty texts', () => {
    for (const key of Object.keys(dicts.nl)) {
      for (const lang of ['fr', 'en'] as const) {
        expect([key, placeholders(dicts[lang][key] ?? '')]).toEqual([key, placeholders(dicts.nl[key] ?? '')]);
        expect((dicts[lang][key] ?? '').trim().length).toBeGreaterThan(0);
      }
    }
  });

  it('translate every machine key the backend sends', () => {
    for (const [ns, keys] of Object.entries(MACHINE_KEYS)) {
      for (const k of keys) {
        for (const lang of ['nl', 'fr', 'en'] as const) {
          const d = dicts[lang];
          expect([lang, `${ns}.${k}`, `${ns}.${k}` in d || `${ns}.${k}.title` in d]).toEqual([lang, `${ns}.${k}`, true]);
        }
      }
    }
  });
});

describe('translator', () => {
  it('interpolates and falls back to Dutch, then to the key', () => {
    const tr = createTranslator({ nl: { a: 'Hallo {name}', b: 'B' }, fr: { a: 'Bonjour {name}' }, en: {} }, 'fr');
    expect(tr.t('a', { name: 'Sanne' })).toBe('Bonjour Sanne');
    expect(tr.t('b')).toBe('B');
    expect(tr.t('missing.key')).toBe('missing.key');
    expect(interpolate('{x} and {y}', { x: 1 })).toBe('1 and {y}');
  });

  it('translates machine keys with the server label as fallback', () => {
    const tr = createTranslator({ nl: dicts.nl, fr: dicts.fr, en: dicts.en }, 'en');
    expect(tr.tk('status', 'secured', 'Je borg is geregistreerd')).toBe('Your deposit is registered');
    expect(tr.tk('status', 'brand_new_status', 'Nieuw label')).toBe('Nieuw label');
    expect(tr.tk('errors', 'partner_unavailable')).toBe('Not available yet.');
  });

  it('picks nl, fr or en from the phone, Dutch otherwise', () => {
    expect(pickLanguage(['fr-BE', 'nl-BE'])).toBe('fr');
    expect(pickLanguage(['en-GB'])).toBe('en');
    expect(pickLanguage(['de-DE'])).toBe('nl');
    expect(pickLanguage([])).toBe('nl');
  });
});
