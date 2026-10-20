/** Combined history: deposit events and investment transactions, newest first (paginated). */
import { router, type Href } from 'expo-router';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { ActivityItem } from '../../../src/api/schemas';
import { usePaged } from '../../../src/hooks/usePaged';
import { useSensitiveScreen } from '../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { eventText } from '../../../src/lib/eventText';
import { formatDate, formatDateTime } from '../../../src/lib/format';
import { formatSignedMoney } from '../../../src/lib/money';
import { ErrorState } from '../../../src/ui/feedback';
import { ListScreen } from '../../../src/ui/ListScreen';
import { AppText } from '../../../src/ui/Text';
import { radius, space, useTheme } from '../../../src/ui/theme';

export default function Activity() {
  useSensitiveScreen();
  const { t } = useI18n();
  const q = usePaged<ActivityItem>(['activity'], (cursor) => api.activity(cursor));
  return (
    <ListScreen
      data={q.items}
      keyExtractor={(i) => `${i.type}-${i.id}`}
      renderItem={({ item }) => <ActivityRow item={item} />}
      loading={q.isLoading}
      loadingMore={q.isFetchingNextPage}
      hasMore={!!q.hasNextPage}
      onLoadMore={() => void q.fetchNextPage()}
      refreshing={q.isRefetching}
      onRefresh={() => void q.refetch()}
      bottomInset={false}
      emptyText={q.error ? undefined : t('activity.empty')}
      header={
        <View style={styles.header}>
          <AppText muted>{t('activity.intro')}</AppText>
          {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}
        </View>
      }
    />
  );
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const tr = useI18n();
  const { colors } = useTheme();
  const isInvest = item.type === 'invest_transaction';
  const title = eventText(item, tr);
  const where = isInvest ? tr.t('activity.invest') : tr.t('activity.deposit', { reference: item.deposit_reference ?? '' });
  const when = isInvest && item.day ? formatDate(item.day, tr.lang) : formatDateTime(item.at, tr.lang);
  const amount = item.amount ? formatSignedMoney(item.amount, tr.lang) : null;
  const go = item.deposit_pid ? () => router.push(`/deposit/${encodeURIComponent(item.deposit_pid as string)}` as Href) : isInvest ? () => router.push('/invest') : undefined;
  return (
    <Pressable
      disabled={!go}
      onPress={go}
      accessibilityRole={go ? 'button' : undefined}
      accessibilityLabel={[title, amount, where, when].filter(Boolean).join(', ')}
      style={({ pressed }) => [styles.row, { backgroundColor: pressed ? colors.surfaceAlt : colors.surface, borderColor: colors.line }]}
    >
      <View style={styles.text}>
        <AppText variant="bodyStrong">{title}</AppText>
        <AppText variant="small" muted>
          {where} · {when}
        </AppText>
      </View>
      {amount ? (
        <AppText variant="money" color={item.amount && item.amount.cents < 0 ? colors.text : colors.okText}>
          {amount}
        </AppText>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: { gap: space.m, marginBottom: space.m },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.m, padding: space.l, borderRadius: radius.m, borderWidth: 1, flexWrap: 'wrap' },
  text: { flex: 1, minWidth: 180, gap: 2 },
});
