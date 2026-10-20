/** Labels for deposit states and places, translated from stable keys with the server's text as fallback. */
import type { Translator } from '../i18n/core';

export function depositStatusLabel(d: { display_key: string; display_label: string }, tr: Translator): string {
  if (tr.has(`display.${d.display_key}`)) return tr.t(`display.${d.display_key}`);
  if (tr.has(`status.${d.display_key}`)) return tr.t(`status.${d.display_key}`);
  return d.display_label;
}

/** Where the deposit sits: Depiqo's account, or the kind of provider elsewhere. */
export function providerKindLabel(holding: string, kind: string | null, fallback: string | null, tr: Translator): string {
  const key = holding === 'depiqo' ? 'depiqo_account' : kind ?? 'unknown';
  if (tr.has(`provider.${key}`)) return tr.t(`provider.${key}`);
  return fallback ?? key;
}

export function addressLine(a: { street: string; postcode: string | null; city: string | null }): string {
  return [a.street, [a.postcode, a.city].filter(Boolean).join(' ')].filter(Boolean).join(', ');
}
