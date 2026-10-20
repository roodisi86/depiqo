/** My deposits: one card per deposit with status and the four separate amounts. */
import { useQueryClient } from '@tanstack/react-query';
import { router, type Href } from 'expo-router';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { DepositSummary } from '../../../src/api/schemas';
import { usePaged } from '../../../src/hooks/usePaged';
import { useSensitiveScreen } from '../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { depositStatusLabel, providerKindLabel } from '../../../src/lib/display';
import { PushPromptCard } from '../../../src/notifications/PushPromptCard';
import { AmountsBlock } from '../../../src/ui/AmountsBlock';
import { ErrorState } from '../../../src/ui/feedback';
import { ListScreen } from '../../../src/ui/ListScreen';
import { StatusPill } from '../../../src/ui/StatusPill';
import { AppText } from '../../../src/ui/Text';
import { radius, space, useTheme } from '../../../src/ui/theme';

export default function Deposits() {
  useSensitiveScreen();
  const { t } = useI18n();
  const qc = useQueryClient();
  const q = usePaged<DepositSummary>(['deposits'], (cursor) => api.deposits(cursor));

  return (
    <ListScreen
      data={q.items}
      keyExtractor={(d) => d.pid}
      renderItem={({ item }) => <DepositCard d={item} />}
      loading={q.isLoading}
      loadingMore={q.isFetchingNextPage}
      hasMore={!!q.hasNextPage}
      onLoadMore={() => void q.fetchNextPage()}
      refreshing={q.isRefetching}
      onRefresh={() => void qc.invalidateQueries()}
      bottomInset={false}
      emptyText={q.error ? undefined : t('deposits.empty')}
      header={
        <View style={styles.header}>
          <AppText muted>{t('deposits.intro')}</AppText>
          <PushPromptCard compact />
          {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}
        </View>
      }
    />
  );
}

function DepositCard({ d }: { d: DepositSummary }) {
  const tr = useI18n();
  const { t } = tr;
  const { colors } = useTheme();
  const address = [d.address.street, d.address.city].filter(Boolean).join(', ');
  const status = depositStatusLabel(d, tr);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${address}. ${status}. ${d.landlord.name}`}
      accessibilityHint={t('deposits.openHint')}
      testID="deposit-card"
      onPress={() => router.push(`/deposit/${encodeURIComponent(d.pid)}` as Href)}
      style={({ pressed }) => [styles.card, { backgroundColor: colors.surface, borderColor: pressed ? colors.primary : colors.line }]}
    >
      <View style={styles.top}>
        <AppText variant="heading">{address}</AppText>
        <AppText variant="small" muted>
          {d.landlord.name} · {d.reference}
        </AppText>
        <StatusPill label={status} tone={d.tone} />
      </View>
      <AmountsBlock amounts={d.amounts} compact />
      <AppText variant="small" muted>
        {providerKindLabel(d.holding, d.provider_kind, null, tr)}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: { gap: space.m, marginBottom: space.m },
  card: { borderWidth: 1.5, borderRadius: radius.m, padding: space.l, gap: space.m },
  top: { gap: space.xs },
});
