import { useQuery } from '@tanstack/react-query';

import { api } from '../api/instance';
import { useAuth } from '../auth/AuthProvider';
import { INVEST_BUILD_ENABLED } from '../config/env';
import { investGate, type InvestGate } from '../lib/investGate';
import { useConfig } from './useConfig';

export const meKey = ['me'] as const;

export function useMe() {
  const { status } = useAuth();
  return useQuery({ queryKey: meKey, queryFn: api.me, enabled: status === 'signedIn', staleTime: 60_000 });
}

/** 'available' only when this build includes Invest, /config offers it AND /me says this tenant is eligible. */
export function useInvestGate(): InvestGate {
  const me = useMe();
  const config = useConfig();
  return investGate(me.data, config.data, INVEST_BUILD_ENABLED);
}
