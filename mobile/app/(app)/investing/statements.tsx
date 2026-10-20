/** Monthly statements of the investment account as PDF. */
import { useQuery } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import React from 'react';

import { downloadAndShare } from '../../../src/api/download';
import { api } from '../../../src/api/instance';
import { useAuth } from '../../../src/auth/AuthProvider';
import { useSafeMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatPeriod } from '../../../src/lib/format';
import { FormError, NotYetAvailable } from '../../../src/ui/feedback';
import { InvestGuard, InvestQueryState, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Screen } from '../../../src/ui/layout';
import { ListItem } from '../../../src/ui/ListItem';
import { AppText } from '../../../src/ui/Text';

export default function StatementsScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('statements.title')}>
      <Statements />
    </InvestGuard>
  );
}

function Statements() {
  const { t, lang } = useI18n();
  const auth = useAuth();
  const q = useQuery({ queryKey: ['invest', 'statements'], queryFn: api.statements, retry: false });
  const open = useSafeMutation((s: { period: string; download_path: string }) =>
    auth.withLockSuspended(() => downloadAndShare(s.download_path, `depiqo-beleggen-${s.period}.pdf`, 'application/pdf', t('statements.title'))),
  );
  const state = InvestQueryState({ isLoading: q.isLoading, error: q.error, onRetry: () => void q.refetch(), title: t('statements.title') });
  if (state) return state;
  if (!q.data) return null;
  if (isPartnerDown(open.error)) return <NotYetAvailable />;
  return (
    <Screen refreshing={q.isRefetching} onRefresh={() => void q.refetch()}>
      <Stack.Screen options={{ title: t('statements.title') }} />
      <AppText muted>{t('statements.intro')}</AppText>
      <FormError error={open.error} />
      <Card>
        {q.data.items.length === 0 ? <AppText muted>{t('statements.empty')}</AppText> : null}
        {q.data.items.map((s) => (
          <ListItem key={s.period} icon="document-outline" title={formatPeriod(s.period, lang)} subtitle={t('statements.pdf')} onPress={() => open.submit(s)} />
        ))}
      </Card>
    </Screen>
  );
}
