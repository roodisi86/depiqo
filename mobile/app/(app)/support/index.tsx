/** My questions to Depiqo support, with status and replies. */
import { router, Stack, type Href } from 'expo-router';
import React from 'react';
import { View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { SupportTicket } from '../../../src/api/schemas';
import { usePaged } from '../../../src/hooks/usePaged';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatDateTime } from '../../../src/lib/format';
import { Button } from '../../../src/ui/Button';
import { ErrorState } from '../../../src/ui/feedback';
import { Card } from '../../../src/ui/layout';
import { ListItem } from '../../../src/ui/ListItem';
import { ListScreen } from '../../../src/ui/ListScreen';
import { AppText } from '../../../src/ui/Text';

export default function SupportList() {
  const { t, tk, lang } = useI18n();
  const q = usePaged<SupportTicket>(['support'], (cursor) => api.supportTickets(cursor));
  return (
    <>
      <Stack.Screen options={{ title: t('support.title') }} />
      <ListScreen
        data={q.items}
        keyExtractor={(x) => String(x.id)}
        renderItem={({ item }) => (
          <Card>
            <ListItem
              title={item.subject}
              subtitle={`${tk('supportCategory', item.category, item.category_label)} · ${tk('supportStatus', item.status, item.status_label)} · ${formatDateTime(item.updated_at, lang)}`}
              onPress={() => router.push(`/support/${item.id}` as Href)}
            />
          </Card>
        )}
        loading={q.isLoading}
        loadingMore={q.isFetchingNextPage}
        hasMore={!!q.hasNextPage}
        onLoadMore={() => void q.fetchNextPage()}
        refreshing={q.isRefetching}
        onRefresh={() => void q.refetch()}
        emptyText={q.error ? undefined : t('support.empty')}
        header={
          <View style={{ gap: 12, marginBottom: 12 }}>
            <AppText muted>{t('support.intro')}</AppText>
            <Button label={t('support.new')} onPress={() => router.push('/support/new')} />
            {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}
          </View>
        }
      />
    </>
  );
}
