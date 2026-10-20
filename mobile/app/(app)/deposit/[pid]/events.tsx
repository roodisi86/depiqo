/** History of one deposit (paginated). */
import { Stack, useLocalSearchParams } from 'expo-router';
import React from 'react';

import { api } from '../../../../src/api/instance';
import type { DepositEvent } from '../../../../src/api/schemas';
import { usePaged } from '../../../../src/hooks/usePaged';
import { useI18n } from '../../../../src/i18n/I18nProvider';
import { eventText } from '../../../../src/lib/eventText';
import { formatDateTime } from '../../../../src/lib/format';
import { ErrorState } from '../../../../src/ui/feedback';
import { Card } from '../../../../src/ui/layout';
import { ListScreen } from '../../../../src/ui/ListScreen';
import { AppText } from '../../../../src/ui/Text';

export default function DepositEvents() {
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const tr = useI18n();
  const q = usePaged<DepositEvent>(['deposit', pid, 'events'], (cursor) => api.depositEvents(pid, cursor), !!pid);
  return (
    <>
      <Stack.Screen options={{ title: tr.t('events.title') }} />
      <ListScreen
        data={q.items}
        keyExtractor={(e) => String(e.id)}
        renderItem={({ item }) => (
          <Card>
            <AppText variant="small" muted>
              {formatDateTime(item.at, tr.lang)} · {tr.tk('actor', item.actor, item.actor)}
            </AppText>
            <AppText variant="bodyStrong">{eventText(item, tr)}</AppText>
          </Card>
        )}
        loading={q.isLoading}
        loadingMore={q.isFetchingNextPage}
        hasMore={!!q.hasNextPage}
        onLoadMore={() => void q.fetchNextPage()}
        refreshing={q.isRefetching}
        onRefresh={() => void q.refetch()}
        emptyText={q.error ? undefined : tr.t('events.empty')}
        header={q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}
      />
    </>
  );
}
