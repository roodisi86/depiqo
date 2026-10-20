import { createIdempotencyKeyHolder, fingerprint, isValidIdempotencyKey } from '../idempotency';

describe('Idempotency-Key per user action', () => {
  let n = 0;
  const newKey = () => `key-${String((n += 1)).padStart(8, '0')}`;

  it('reuses the key while the same action is retried', () => {
    const h = createIdempotencyKeyHolder(newKey);
    const a = h.keyFor(fingerprint({ amount_cents: 1000 }));
    const b = h.keyFor(fingerprint({ amount_cents: 1000 }));
    expect(a).toBe(b);
    expect(isValidIdempotencyKey(a)).toBe(true);
  });

  it('uses a new key when the payload changes (a different action)', () => {
    const h = createIdempotencyKeyHolder(newKey);
    const a = h.keyFor(fingerprint({ amount_cents: 1000 }));
    const b = h.keyFor(fingerprint({ amount_cents: 2000 }));
    expect(a).not.toBe(b);
  });

  it('uses a new key after success', () => {
    const h = createIdempotencyKeyHolder(newKey);
    const a = h.keyFor('x');
    h.reset();
    expect(h.current()).toBeNull();
    expect(h.keyFor('x')).not.toBe(a);
  });

  it('treats objects with the same content in another key order as the same action', () => {
    expect(fingerprint({ a: 1, b: { c: 2, d: 3 } })).toBe(fingerprint({ b: { d: 3, c: 2 }, a: 1 }));
  });

  it('only accepts keys the server accepts (8 to 100 of A-Z a-z 0-9 _ - : .)', () => {
    expect(isValidIdempotencyKey('7c1f0d2e-order-1')).toBe(true);
    expect(isValidIdempotencyKey('3b241101-e2bb-4255-8caf-4136c566a962')).toBe(true);
    expect(isValidIdempotencyKey('short')).toBe(false);
    expect(isValidIdempotencyKey('has space in it')).toBe(false);
    expect(() => createIdempotencyKeyHolder(() => 'bad').keyFor('x')).toThrow();
  });
});
