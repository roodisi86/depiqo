/** In-app notifications (title and text come from the server in the app's language). Tap: mark read and open. */
import { useQueryClient } from '@tanstack/react-query';
import { router, type Href } from 'expo-router';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { AppNotification } from '../../../src/api/schemas';
import { usePaged } from '../../../src/hooks/usePaged';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { parseDeepLink, routeFor } from '../../../src/lib/deeplink';
import { formatDateTime } from '../../../src/lib/format';
import { PushPromptCard } from '../../../src/notifications/PushPromptCard';
import { ErrorState } from '../../../src/ui/feedback';
import { ListScreen } from '../../../src/ui/ListScreen';
import { AppText } from '../../../src/ui/Text';
import { radius, space, useTheme } from '../../../src/ui/theme';

export default function Notifications() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const q = usePaged<AppNotification>(['notifications', 'list'], (cursor) => api.notifications(cursor));

  const open = async (n: AppNotification) => {
    if (!n.read_at) {
      try {
        await api.markNotificationRead(n.id);
        await qc.invalidateQueries({ queryKey: ['notifications'] });
      } catch {
        // reading still works; the dot stays until next time
      }
    }
    const link = parseDeepLink(n.link_path);
    if (link) router.push(routeFor(link) as Href);
  };

  return (
    <ListScreen
      data={q.items}
      keyExtractor={(n) => String(n.id)}
      renderItem={({ item }) => <NotificationRow n={item} onPress={() => void open(item)} />}
      loading={q.isLoading}
      loadingMore={q.isFetchingNextPage}
      hasMore={!!q.hasNextPage}
      onLoadMore={() => void q.fetchNextPage()}
      refreshing={q.isRefetching}
      onRefresh={() => void qc.invalidateQueries({ queryKey: ['notifications'] })}
      bottomInset={false}
      emptyText={q.error ? undefined : t('notifications.empty')}
      header={
        <View style={styles.header}>
          <PushPromptCard />
          {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}
        </View>
      }
    />
  );
}

function NotificationRow({ n, onPress }: { n: AppNotification; onPress: () => void }) {
  const { t, lang } = useI18n();
  const { colors } = useTheme();
  const unread = !n.read_at;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      testID="notification-row"
      accessibilityLabel={`${unread ? `${t('notifications.unread')}. ` : ''}${n.title}. ${n.body}. ${formatDateTime(n.created_at, lang)}`}
      style={({ pressed }) => [styles.row, { backgroundColor: pressed ? colors.surfaceAlt : colors.surface, borderColor: unread ? colors.primary : colors.line }]}
    >
      <View style={[styles.dot, { backgroundColor: unread ? colors.primary : 'transparent' }]} />
      <View style={styles.text}>
        <AppText variant={unread ? 'bodyStrong' : 'body'}>{n.title}</AppText>
        <AppText variant="small">{n.body}</AppText>
        <AppText variant="small" muted>
          {formatDateTime(n.created_at, lang)}
        </AppText>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: { gap: space.m, marginBottom: space.m },
  row: { flexDirection: 'row', gap: space.m, padding: space.l, borderRadius: radius.m, borderWidth: 1.5 },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 7 },
  text: { flex: 1, gap: 2 },
});
