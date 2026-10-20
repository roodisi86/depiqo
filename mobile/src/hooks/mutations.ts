/**
 * Mutations that cannot fire twice: a synchronous in-flight guard (a second tap before React re-renders
 * is ignored) plus `busy` for disabling the button. Money-related writes also carry an Idempotency-Key:
 * one per user action, reused when the same action is retried.
 */
import { useMutation } from '@tanstack/react-query';
import * as Crypto from 'expo-crypto';
import { useCallback, useRef } from 'react';

import { createIdempotencyKeyHolder, fingerprint } from '../api/idempotency';

export function useSafeMutation<TVars, TData>(
  fn: (vars: TVars) => Promise<TData>,
  opts?: { onSuccess?: (data: TData, vars: TVars) => void | Promise<void> },
) {
  const inFlight = useRef(false);
  const m = useMutation<TData, unknown, TVars>({
    mutationFn: fn,
    retry: false,
    onSuccess: async (data, vars) => {
      await opts?.onSuccess?.(data, vars);
    },
    onSettled: () => {
      inFlight.current = false;
    },
  });
  const { mutate } = m;
  const submit = useCallback(
    (vars: TVars) => {
      if (inFlight.current) return;
      inFlight.current = true;
      mutate(vars);
    },
    [mutate],
  );
  return { ...m, submit, busy: m.isPending };
}

export function useIdempotentMutation<TVars, TData>(
  fn: (vars: TVars, idempotencyKey: string) => Promise<TData>,
  opts?: { fingerprint?: (vars: TVars) => unknown; onSuccess?: (data: TData, vars: TVars) => void | Promise<void> },
) {
  const holder = useRef(createIdempotencyKeyHolder(() => Crypto.randomUUID())).current;
  return useSafeMutation<TVars, TData>(
    (vars) => fn(vars, holder.keyFor(fingerprint(opts?.fingerprint ? opts.fingerprint(vars) : vars))),
    {
      onSuccess: async (data, vars) => {
        holder.reset();
        await opts?.onSuccess?.(data, vars);
      },
    },
  );
}
