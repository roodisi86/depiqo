/**
 * The only place that may write to the console. Silent outside development builds, and everything
 * passes through redact() first. Do not log API responses, tokens or personal data.
 */
import { APP_ENV } from '../config/env';
import { redact } from './redact';

export const log = {
  warn(message: string, detail?: unknown): void {
    if (APP_ENV !== 'development') return;
    console.warn(`[depiqo] ${message}`, detail === undefined ? '' : redact(detail));
  },
};
