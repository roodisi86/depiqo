/** One support question with the conversation. */
import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useEffect } from 'react';
import { View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { SupportTicket } from '../../../src/api/schemas';
import { usePaged } from '../../../src/hooks/usePaged';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatDateTime } from '../../../src/lib/format';
import { ErrorState, Loading, Notice } from '../../../src/ui/feedback';
import { Card, Screen } from '../../../src/ui/layout';
import { StatusPill } from '../../../src/ui/StatusPill';
import { AppText } from '../../../src/ui/Text';
import { useTheme } from '../../../src/ui/theme';

export default function Ticket() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t, tk, lang } = useI18n();
  const { colors } = useTheme();
  // There is no GET /support/{id}: the ticket comes from the (paged) list.
  const q = usePaged<SupportTicket>(['support'], (cursor) => api.supportTickets(cursor, 50));
  const ticket = q.items.find((x) => String(x.id) === id);
  const title = <Stack.Screen options={{ title: ticket ? ticket.subject : t('support.title') }} />;
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = q;
  const found = !!ticket;

  useEffect(() => {
    // Older questions are further down the list: keep loading pages until it is found or the list ends.
    if (!found && hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [found, hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (q.isLoading) return <Loading />;
  if (!ticket) {
    return (
      <Screen>
        {title}
        {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : q.isFetchingNextPage ? <Loading /> : <Notice tone="info">{t('support.notFound')}</Notice>}
      </Screen>
    );
  }
  return (
    <Screen refreshing={q.isRefetching} onRefresh={() => void q.refetch()}>
      {title}
      <StatusPill label={tk('supportStatus', ticket.status, ticket.status_label)} tone={ticket.status === 'answered' ? 'ok' : ticket.status === 'open' ? 'wait' : 'neutral'} />
      <AppText muted>{tk('supportCategory', ticket.category, ticket.category_label)}</AppText>
      {ticket.messages.map((m, i) => {
        const mine = m.author === 'tenant';
        return (
          <View key={`${m.created_at}-${i}`} style={{ alignItems: mine ? 'flex-end' : 'flex-start' }}>
            <Card style={{ maxWidth: '92%', backgroundColor: mine ? colors.surfaceAccent : colors.surface }}>
              <AppText variant="label" muted>
                {mine ? t('support.you') : t('support.depiqo')} · {formatDateTime(m.created_at, lang)}
              </AppText>
              <AppText selectable>{m.body}</AppText>
            </Card>
          </View>
        );
      })}
      {ticket.status === 'open' ? <Notice tone="info">{t('support.waiting')}</Notice> : null}
    </Screen>
  );
}
