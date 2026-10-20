/**
 * Redaction for anything that might end up in a log (pure). Tokens, passwords, codes, IBANs, e-mail
 * addresses and names are replaced. The app logs almost nothing; this is the safety net.
 */
const SECRET_KEY = /token|password|authorization|secret|code|iban|email|name|birth|reason|message|body/i;
const BEARER = /Bearer\s+[A-Za-z0-9._~+/=-]+/g;
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const IBAN = /\b[A-Z]{2}\d{2}[A-Z0-9]{8,30}\b/g;
const EXPO_TOKEN = /Expo(nent)?PushToken\[[^\]]+\]/g;

export function redactString(s: string): string {
  return s
    .replace(BEARER, 'Bearer [redacted]')
    .replace(EXPO_TOKEN, 'ExpoPushToken[redacted]')
    .replace(EMAIL, '[email]')
    .replace(IBAN, '[iban]');
}

export function redact(value: unknown, depth = 0): unknown {
  if (depth > 6) return '[deep]';
  if (typeof value === 'string') return redactString(value);
  if (Array.isArray(value)) return value.map((v) => redact(v, depth + 1));
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = SECRET_KEY.test(k) ? '[redacted]' : redact(v, depth + 1);
    }
    return out;
  }
  return value;
}
