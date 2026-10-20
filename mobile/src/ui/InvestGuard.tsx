/**
 * Every Invest screen sits inside this guard: hidden or not eligible -> "Nog niet beschikbaar";
 * partner_unavailable from the API -> "Nog niet beschikbaar" and nothing else.
 */
import { Stack } from 'expo-router';
import React from 'react';

import { hasCode } from '../api/errors';
import { useInvestGate } from '../hooks/useMe';
import { useI18n } from '../i18n/I18nProvider';
import { ErrorState, Loading, Notice, NotYetAvailable } from './feedback';
import { Screen } from './layout';

export function InvestGuard({ title, children, edges }: { title?: string; children: React.ReactNode; edges?: ('top' | 'bottom')[] }) {
  const gate = useInvestGate();
  if (gate !== 'available') {
    return (
      <Screen edges={edges}>
        {title ? <Stack.Screen options={{ title }} /> : null}
        <NotYetAvailable />
      </Screen>
    );
  }
  return <>{children}</>;
}

/** Loading and error states for an Invest query. Returns null when there is data to show. */
export function InvestQueryState({ isLoading, error, onRetry, title, edges }: { isLoading: boolean; error: unknown; onRetry: () => void; title?: string; edges?: ('top' | 'bottom')[] }) {
  const { t } = useI18n();
  if (isLoading) return <Loading />;
  if (!error) return null;
  return (
    <Screen edges={edges}>
      {title ? <Stack.Screen options={{ title }} /> : null}
      {hasCode(error, 'partner_unavailable') ? (
        <NotYetAvailable />
      ) : hasCode(error, 'invest_not_offered') ? (
        <Notice tone="info" title={t('errors.invest_not_offered')} />
      ) : (
        <ErrorState error={error} onRetry={onRetry} />
      )}
    </Screen>
  );
}

/** Mutation errors on Invest screens: partner_unavailable replaces the whole screen. */
export function isPartnerDown(error: unknown): boolean {
  return hasCode(error, 'partner_unavailable');
}
