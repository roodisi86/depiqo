/**
 * Text for a deposit event or activity item, translated from its stable key and parameters
 * (status_changed + to_status, payment_received + amount_cents...). Falls back to the server's Dutch text.
 */
import type { Translator } from '../i18n/core';
import { formatCents } from './money';

interface EventLike {
  key: string;
  params: Record<string, unknown>;
  message: string | null;
}

export function eventText(e: EventLike, tr: Translator): string {
  const p = e.params ?? {};
  const cents = typeof p.amount_cents === 'number' ? p.amount_cents : null;
  switch (e.key) {
    case 'status_changed': {
      const to = typeof p.to_status === 'string' ? p.to_status : null;
      if (!to) return e.message ?? tr.t('event.status_changed_plain');
      return tr.t('event.status_changed', { status: tr.tk('status', to, to) });
    }
    case 'payment_received':
    case 'interest_credited':
      return cents !== null ? tr.t(`event.${e.key}`, { amount: formatCents(cents, tr.lang) }) : e.message ?? tr.t(`event.${e.key}_plain`);
    default: {
      const key = `event.${e.key}`;
      if (tr.has(key)) return tr.t(key);
      return e.message ?? e.key;
    }
  }
}
