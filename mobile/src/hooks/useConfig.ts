import { useQuery } from '@tanstack/react-query';

import { api } from '../api/instance';

export const configKey = ['config'] as const;

/** GET /config: environment banner, minimum versions, feature flags and links. Works signed out. */
export function useConfig() {
  return useQuery({ queryKey: configKey, queryFn: api.config, staleTime: 5 * 60_000, retry: 2 });
}
