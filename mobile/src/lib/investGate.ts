/**
 * Whether Depiqo Invest is shown at all (pure).
 *
 * Shown only when ALL of:
 *   - this build includes Invest (INVEST_ENABLED at build time; off in production builds by default),
 *   - /config says the feature exists (features.invest is true, "per_user", "available" or "on"), and
 *   - /me says this tenant is eligible (invest.eligible === true and invest.visibility === "available").
 * Anything missing, unknown or false hides it. A partner_unavailable answer from any Invest endpoint
 * shows "Nog niet beschikbaar" and nothing else (see isPartnerUnavailable and NotYetAvailable).
 */
import { hasCode } from '../api/errors';

export type InvestGate = 'hidden' | 'available';

interface MeLike {
  invest?: { eligible?: boolean; visibility?: string } | null;
}

interface ConfigLike {
  features?: Record<string, unknown> | null;
}

const ON_VALUES: readonly unknown[] = [true, 'per_user', 'available', 'on'];

export function investFeatureOn(config: ConfigLike | null | undefined): boolean {
  const v = config?.features?.invest;
  return ON_VALUES.includes(v);
}

export function investGate(me: MeLike | null | undefined, config: ConfigLike | null | undefined, buildEnabled = true): InvestGate {
  if (!buildEnabled) return 'hidden';
  if (!me || !config) return 'hidden';
  if (!investFeatureOn(config)) return 'hidden';
  if (me.invest?.eligible === true && me.invest.visibility === 'available') return 'available';
  return 'hidden';
}

export function isPartnerUnavailable(err: unknown): boolean {
  return hasCode(err, 'partner_unavailable');
}
