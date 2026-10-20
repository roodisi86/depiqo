/**
 * Idempotency-Key handling (pure).
 *
 * One key per user action. A retry of the same action (same payload) reuses the key, so the server
 * returns the stored answer instead of doing the action twice. A changed payload is a new action and
 * gets a new key (the server would refuse a reused key with a different body: idempotency_key_reused).
 * After success the key is dropped.
 */
const KEY_PATTERN = /^[A-Za-z0-9_\-:.]{8,100}$/;

export function isValidIdempotencyKey(key: string): boolean {
  return KEY_PATTERN.test(key);
}

export interface IdempotencyKeyHolder {
  /** The key for this payload: the pending one when the payload is unchanged, else a fresh one. */
  keyFor(fingerprint: string): string;
  /** Forget the pending key (call after success). */
  reset(): void;
  /** The pending key, if any. */
  current(): string | null;
}

export function createIdempotencyKeyHolder(newKey: () => string): IdempotencyKeyHolder {
  let pendingFingerprint: string | null = null;
  let pendingKey: string | null = null;
  return {
    keyFor(fingerprint: string): string {
      if (pendingKey === null || pendingFingerprint !== fingerprint) {
        const key = newKey();
        if (!isValidIdempotencyKey(key)) throw new Error('invalid idempotency key generated');
        pendingKey = key;
        pendingFingerprint = fingerprint;
      }
      return pendingKey;
    },
    reset(): void {
      pendingKey = null;
      pendingFingerprint = null;
    },
    current(): string | null {
      return pendingKey;
    },
  };
}

/** A stable text for a payload: object keys sorted, so {a,b} and {b,a} are the same action. */
export function fingerprint(value: unknown): string {
  return JSON.stringify(sortKeys(value)) ?? '';
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(value as Record<string, unknown>).sort()) out[k] = sortKeys((value as Record<string, unknown>)[k]);
    return out;
  }
  return value;
}
