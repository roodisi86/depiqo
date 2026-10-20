/**
 * The four amounts are strictly separate: unknown shows "—" with the explanation, and the required
 * amount is never shown as money that is held.
 */
import { amountViews, type AmountLike } from '../amounts';
import { formatCents, formatMoney, UNKNOWN } from '../money';

const eur = (cents: number) => ({ cents, currency: 'EUR' });

const GUARANTEE: AmountLike[] = [
  { key: 'obligation', value: eur(250000), known: true, explanation: 'Volgens het huurcontract', explanation_key: 'per_lease' },
  { key: 'received', value: null, known: false, explanation: 'Geen geld gestort: een derde staat garant', explanation_key: 'guarantee_no_money' },
  { key: 'locked', value: null, known: false, explanation: 'Geen juridische blokkering aangetoond', explanation_key: 'no_legal_lock' },
  { key: 'interest', value: null, known: false, explanation: 'Valt buiten Depiqo bij een borg elders', explanation_key: 'outside_depiqo' },
];

describe('amount display', () => {
  it('shows "—" with the explanation when a value is null', () => {
    const v = amountViews(GUARANTEE, 'nl');
    expect(v.map((x) => x.key)).toEqual(['obligation', 'received', 'locked', 'interest']);
    expect(v[0]?.display).toBe(formatCents(250000, 'nl'));
    for (const x of v.slice(1)) {
      expect(x.display).toBe(UNKNOWN);
      expect(x.known).toBe(false);
      expect(x.explanationKey).not.toBeNull();
    }
  });

  it('never falls back to the required amount for received, locked or interest', () => {
    const required = formatCents(250000, 'nl');
    for (const lang of ['nl', 'fr', 'en'] as const) {
      const v = amountViews(GUARANTEE, lang);
      for (const x of v.filter((y) => y.key !== 'obligation')) {
        expect(x.display).not.toBe(formatCents(250000, lang));
        expect(x.display).not.toContain('2.500');
        expect(x.display).not.toContain('2,500');
      }
      expect(v.filter((x) => x.display === required)).toHaveLength(lang === 'nl' ? 1 : 0);
    }
  });

  it('shows "—" when known is false even if a value came along', () => {
    const odd: AmountLike[] = [{ key: 'locked', value: eur(250000), known: false, explanation: 'x', explanation_key: 'lock_requested' }];
    const locked = amountViews(odd, 'nl').find((x) => x.key === 'locked');
    expect(locked?.display).toBe(UNKNOWN);
  });

  it('shows four rows even when the server sent fewer, missing ones as "—"', () => {
    const v = amountViews([GUARANTEE[0] as AmountLike], 'en');
    expect(v).toHaveLength(4);
    expect(v.slice(1).every((x) => x.display === UNKNOWN && x.explanationKey === null)).toBe(true);
  });

  it('shows each known amount as its own value (no sums)', () => {
    const full: AmountLike[] = [
      { key: 'obligation', value: eur(310000), known: true, explanation: '', explanation_key: 'per_lease' },
      { key: 'received', value: eur(310000), known: true, explanation: '', explanation_key: 'bank_confirmed' },
      { key: 'locked', value: eur(314682), known: true, explanation: '', explanation_key: 'lock_confirmed_by_bank' },
      { key: 'interest', value: eur(4682), known: true, explanation: '', explanation_key: 'interest_credited' },
    ];
    expect(amountViews(full, 'en').map((x) => x.display)).toEqual(['€3,100.00', '€3,100.00', '€3,146.82', '€46.82']);
  });
});

describe('money formatting', () => {
  it('formats per language like the backend', () => {
    expect(formatCents(123456, 'nl')).toBe('€\u00A01.234,56');
    expect(formatCents(123456, 'fr')).toBe('1\u202F234,56\u00A0€');
    expect(formatCents(123456, 'en')).toBe('€1,234.56');
    expect(formatCents(-14999, 'en')).toBe('\u2212€149.99');
    expect(formatCents(5, 'nl')).toBe('€\u00A00,05');
  });

  it('shows "—" for null, undefined and other currencies', () => {
    expect(formatMoney(null, 'nl')).toBe(UNKNOWN);
    expect(formatMoney(undefined, 'nl')).toBe(UNKNOWN);
    expect(formatMoney({ cents: 100, currency: 'USD' }, 'nl')).toBe(UNKNOWN);
  });
});
