/**
 * The four deposit amounts, strictly separated (pure).
 *
 *   obligation  Vereiste borg                          what the lease requires
 *   received    Ontvangen                              what was received (proven)
 *   locked      Bevestigd geblokkeerd                  legally locked (juridische zekerheid)
 *   interest    Rente                                  interest credited
 *
 * Each row shows only its own value. Unknown (value null, or known=false) shows "—" with the backend's
 * explanation. The required amount is NEVER used as a stand-in for money that is held, and amounts
 * are never added up.
 */
import { formatMoney, UNKNOWN, type Lang, type MoneyLike } from './money';

export const AMOUNT_KEYS = ['obligation', 'received', 'locked', 'interest'] as const;
export type AmountKey = (typeof AMOUNT_KEYS)[number];

export interface AmountLike {
  key: string;
  value: MoneyLike | null;
  known: boolean;
  explanation: string;
  explanation_key: string;
}

export interface AmountView {
  key: AmountKey;
  /** Formatted money, or "—". */
  display: string;
  known: boolean;
  explanationKey: string | null;
  explanation: string | null;
}

export function amountView(key: AmountKey, amounts: readonly AmountLike[], lang: Lang): AmountView {
  const a = amounts.find((x) => x.key === key);
  if (!a) return { key, display: UNKNOWN, known: false, explanationKey: null, explanation: null };
  const known = a.known === true && a.value !== null;
  return {
    key,
    display: known ? formatMoney(a.value, lang) : UNKNOWN,
    known,
    explanationKey: a.explanation_key || null,
    explanation: a.explanation || null,
  };
}

/** Always four rows, always in the same order, whatever the backend sent. */
export function amountViews(amounts: readonly AmountLike[], lang: Lang): AmountView[] {
  return AMOUNT_KEYS.map((k) => amountView(k, amounts, lang));
}
