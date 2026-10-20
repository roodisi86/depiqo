/** The quote between the trade screen and the risk acknowledgement screen (memory only). */
import type { Quote } from '../api/schemas';

let current: Quote | null = null;

export function setQuote(q: Quote | null): void {
  current = q;
}

export function getQuote(): Quote | null {
  return current;
}
