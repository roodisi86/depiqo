/** Invest is shown only when /config offers it AND /me says the tenant is eligible. */
import { ApiError } from '../../api/errors';
import { investFeatureOn, investGate, isPartnerUnavailable } from '../investGate';

const config = (invest: unknown) => ({ features: { wallet: true, invest } });
const me = (eligible: boolean, visibility: string) => ({ invest: { eligible, visibility, offered_by_landlord: true, account_status: null } });

describe('investGate', () => {
  it('is available when the feature is on and the tenant is eligible', () => {
    expect(investGate(me(true, 'available'), config('per_user'))).toBe('available');
    expect(investGate(me(true, 'available'), config(true))).toBe('available');
  });

  it('is hidden when the tenant is not eligible', () => {
    expect(investGate(me(false, 'hidden'), config('per_user'))).toBe('hidden');
    expect(investGate(me(false, 'unavailable'), config('per_user'))).toBe('hidden');
  });

  it('is hidden when the feature flag is off, missing or unknown', () => {
    expect(investGate(me(true, 'available'), config(false))).toBe('hidden');
    expect(investGate(me(true, 'available'), config('off'))).toBe('hidden');
    expect(investGate(me(true, 'available'), { features: {} })).toBe('hidden');
    expect(investGate(me(true, 'available'), { features: null })).toBe('hidden');
    expect(investFeatureOn(undefined)).toBe(false);
  });

  it('is hidden while /me or /config is not loaded', () => {
    expect(investGate(undefined, config('per_user'))).toBe('hidden');
    expect(investGate(me(true, 'available'), undefined)).toBe('hidden');
  });

  it('requires both eligible and visibility "available"', () => {
    expect(investGate(me(true, 'unavailable'), config('per_user'))).toBe('hidden');
    expect(investGate({ invest: null }, config('per_user'))).toBe('hidden');
  });

  it('is hidden in a build without Invest, whatever the server says', () => {
    expect(investGate(me(true, 'available'), config('per_user'), false)).toBe('hidden');
    expect(investGate(me(true, 'available'), config(true), true)).toBe('available');
  });

  it('recognises partner_unavailable answers', () => {
    expect(isPartnerUnavailable(new ApiError({ status: 503, code: 'partner_unavailable' }))).toBe(true);
    expect(isPartnerUnavailable(new ApiError({ status: 503, code: 'server_error' }))).toBe(false);
    expect(isPartnerUnavailable(new Error('x'))).toBe(false);
  });
});
