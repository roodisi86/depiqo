/** Orders, cash transactions and withdrawals of the investment account (paginated). */
import { Stack } from 'expo-router';
import React, { useState } from 'react';
import { View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { InvestTransaction, Order, Withdrawal } from '../../../src/api/schemas';
import { usePaged } from '../../../src/hooks/usePaged';
import { useSensitiveScreen } from '../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatDate } from '../../../src/lib/format';
import { formatMoney, formatSignedMoney } from '../../../src/lib/money';
import { ErrorState, NotYetAvailable } from '../../../src/ui/feedback';
import { Segmented } from '../../../src/ui/form';
import { InvestGuard, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Row } from '../../../src/ui/layout';
import { ListScreen } from '../../../src/ui/ListScreen';
import { StatusPill } from '../../../src/ui/StatusPill';
import { AppText } from '../../../src/ui/Text';

type Tab = 'orders' | 'transactions' | 'withdrawals';

export default function OrdersScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('orders.title')}>
      <Lists />
    </InvestGuard>
  );
}

function Lists() {
  useSensitiveScreen();
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>('orders');
  const header = (
    <View style={{ marginBottom: 12 }}>
      <Segmented<Tab>
        label={t('orders.title')}
        value={tab}
        onChange={setTab}
        options={[
          { value: 'orders', label: t('orders.tabOrders') },
          { value: 'transactions', label: t('orders.tabTransactions') },
          { value: 'withdrawals', label: t('orders.tabWithdrawals') },
        ]}
      />
    </View>
  );
  return (
    <>
      <Stack.Screen options={{ title: t('orders.title') }} />
      {tab === 'orders' ? <OrdersList header={header} /> : tab === 'transactions' ? <TransactionsList header={header} /> : <WithdrawalsList header={header} />}
    </>
  );
}

function tone(status: string): string {
  if (status === 'executed' || status === 'confirmed') return 'ok';
  if (status === 'failed') return 'alert';
  return 'wait';
}

function OrdersList({ header }: { header: React.ReactElement }) {
  const { t, tk, lang } = useI18n();
  const q = usePaged<Order>(['invest', 'orders'], (c) => api.orders(c));
  if (isPartnerDown(q.error)) return <NotYetAvailable />;
  return (
    <ListScreen
      data={q.items}
      keyExtractor={(o) => String(o.id)}
      header={<>{header}{q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}</>}
      renderItem={({ item: o }) => (
        <Card>
          <AppText variant="bodyStrong">
            {tk('side', o.side, o.side)} · {tk('portfolio', o.portfolio, o.portfolio_label)}
            {o.purpose !== 'order' ? ` · ${tk('orderPurpose', o.purpose, o.purpose)}` : ''}
          </AppText>
          <StatusPill label={tk('orderStatus', o.status, o.status_label)} tone={tone(o.status)} />
          <Row label={t('orders.amount')} value={o.sell_all ? t('orders.sellAll') : formatMoney(o.amount, lang)} />
          <Row label={t('orders.executed')} value={formatMoney(o.executed_amount, lang)} hint={o.executed_day ? formatDate(o.executed_day, lang) : null} />
          <Row label={t('orders.created')} value={formatDate(o.created_at, lang)} />
          {o.error ? <AppText variant="small">{o.error}</AppText> : null}
        </Card>
      )}
      loading={q.isLoading}
      loadingMore={q.isFetchingNextPage}
      hasMore={!!q.hasNextPage}
      onLoadMore={() => void q.fetchNextPage()}
      refreshing={q.isRefetching}
      onRefresh={() => void q.refetch()}
      emptyText={q.error ? undefined : t('orders.empty')}
    />
  );
}

function TransactionsList({ header }: { header: React.ReactElement }) {
  const { t, tk, lang } = useI18n();
  const q = usePaged<InvestTransaction>(['invest', 'transactions'], (c) => api.investTransactions(c));
  if (isPartnerDown(q.error)) return <NotYetAvailable />;
  return (
    <ListScreen
      data={q.items}
      keyExtractor={(x) => String(x.id)}
      header={<>{header}{q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}</>}
      renderItem={({ item: x }) => (
        <Card>
          <Row label={`${formatDate(x.day, lang)} · ${tk('txKind', x.kind, x.kind)}`} value={formatSignedMoney(x.amount, lang)} hint={lang === 'nl' ? x.description : null} />
        </Card>
      )}
      loading={q.isLoading}
      loadingMore={q.isFetchingNextPage}
      hasMore={!!q.hasNextPage}
      onLoadMore={() => void q.fetchNextPage()}
      refreshing={q.isRefetching}
      onRefresh={() => void q.refetch()}
      emptyText={q.error ? undefined : t('orders.emptyTransactions')}
    />
  );
}

function WithdrawalsList({ header }: { header: React.ReactElement }) {
  const { t, tk, lang } = useI18n();
  const q = usePaged<Withdrawal>(['invest', 'withdrawals'], (c) => api.withdrawals(c));
  if (isPartnerDown(q.error)) return <NotYetAvailable />;
  return (
    <ListScreen
      data={q.items}
      keyExtractor={(w) => String(w.id)}
      header={<>{header}{q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}</>}
      renderItem={({ item: w }) => (
        <Card>
          <Row label={`${formatDate(w.day ?? w.created_at, lang)} · ${w.iban_masked}`} value={formatMoney(w.amount, lang)} />
          <StatusPill label={tk('withdrawalStatus', w.status, w.status_label)} tone={tone(w.status)} />
        </Card>
      )}
      loading={q.isLoading}
      loadingMore={q.isFetchingNextPage}
      hasMore={!!q.hasNextPage}
      onLoadMore={() => void q.fetchNextPage()}
      refreshing={q.isRefetching}
      onRefresh={() => void q.refetch()}
      emptyText={q.error ? undefined : t('orders.emptyWithdrawals')}
    />
  );
}
