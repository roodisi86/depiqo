/**
 * Depiqo Invest overview: value, invested, cash, result, positions and a chart from the API series;
 * or the onboarding steps when there is no account yet. Only reachable when /config offers Invest and
 * /me says the tenant is eligible; partner_unavailable shows "Nog niet beschikbaar" only.
 * The deposit is never invested: this is the tenant's own money at a licensed partner.
 */
import { useQuery } from '@tanstack/react-query';
import { router, type Href } from 'expo-router';
import React, { useState } from 'react';
import { View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { InvestOverview } from '../../../src/api/schemas';
import { useSensitiveScreen } from '../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatDate } from '../../../src/lib/format';
import { formatBps, formatMoney, formatPercent, formatSignedMoney } from '../../../src/lib/money';
import { Button } from '../../../src/ui/Button';
import { Notice } from '../../../src/ui/feedback';
import { Segmented } from '../../../src/ui/form';
import { InvestGuard, InvestQueryState } from '../../../src/ui/InvestGuard';
import { Card, Row, Screen, SectionTitle } from '../../../src/ui/layout';
import { LineChart } from '../../../src/ui/LineChart';
import { ListItem } from '../../../src/ui/ListItem';
import { AppText } from '../../../src/ui/Text';
import { space, useTheme } from '../../../src/ui/theme';

type Range = '1M' | '6M' | '1Y' | 'max';

export default function InvestTab() {
  return (
    <InvestGuard edges={[]}>
      <InvestOverviewScreen />
    </InvestGuard>
  );
}

function InvestOverviewScreen() {
  useSensitiveScreen();
  const { t, lang } = useI18n();
  const q = useQuery({ queryKey: ['invest'], queryFn: api.investOverview, retry: false });
  const state = InvestQueryState({ isLoading: q.isLoading, error: q.error, onRetry: () => void q.refetch(), edges: [] });
  if (state) return state;
  if (!q.data) return null;
  const o = q.data;
  const acct = o.account;
  return (
    <Screen edges={[]} refreshing={q.isRefetching} onRefresh={() => void q.refetch()} testID="invest-overview">
      {o.partner.sandbox ? (
        <Notice tone="wait" title={t('invest.sandboxTitle')}>
          {t('invest.sandboxBody', { partner: o.partner.name })}
        </Notice>
      ) : null}
      <Card accent>
        <AppText variant="bodyStrong">{t('invest.separationTitle')}</AppText>
        <AppText>{lang === 'nl' ? o.separation_text : t('invest.separation')}</AppText>
      </Card>

      {o.onboarding ? <Onboarding o={o} /> : null}
      {acct && acct.status === 'pending' ? <Notice tone="info" title={t('invest.accountPendingTitle')}>{t('invest.accountPending')}</Notice> : null}
      {acct?.pending_switch ? <Notice tone="info" title={t('invest.switchPendingTitle')}>{acct.switch_note ?? t('invest.switchPending')}</Notice> : null}
      {acct && acct.pending_fee_bps !== null ? (
        <Notice tone="wait" title={t('invest.feeProposalTitle')}>
          <AppText>{t('invest.feeProposal', { from: formatBps(acct.fee_rate_bps, lang), to: formatBps(acct.pending_fee_bps, lang) })}</AppText>
          <Button label={t('invest.feeProposalOpen')} variant="secondary" compact onPress={() => router.push('/investing/fee-change')} />
        </Notice>
      ) : null}

      {o.summary ? <SummaryCards o={o} /> : null}
      {acct && (acct.status === 'active' || acct.status === 'closed') ? <Actions o={o} /> : null}

      <Notice tone="wait" title={t('invest.riskTitle')}>
        {o.risk_text}
      </Notice>
      <AppText variant="small" muted>
        {o.role_text}
      </AppText>
      {lang !== 'nl' ? (
        <AppText variant="small" muted>
          {t('common.dutchOnly')}
        </AppText>
      ) : null}
      {o.summary ? (
        <AppText variant="small" muted>
          {t('invest.asOf', { date: formatDate(o.summary.day, lang) })}
        </AppText>
      ) : null}
    </Screen>
  );
}

function Onboarding({ o }: { o: InvestOverview }) {
  const { t, tk } = useI18n();
  const step = o.onboarding?.next_step ?? 'appropriateness';
  const order = ['appropriateness', 'terms', 'open_account'];
  const currentIndex = step === 'confirm_warning' ? 0 : order.indexOf(step);
  const target: Record<string, Href> = {
    appropriateness: '/investing/appropriateness',
    confirm_warning: '/investing/appropriateness',
    terms: '/investing/terms',
    open_account: { pathname: '/investing/portfolios', params: { mode: 'open' } } as unknown as Href,
  };
  return (
    <Card>
      <SectionTitle>{t('invest.onboardingTitle')}</SectionTitle>
      <AppText>{t('invest.onboardingIntro')}</AppText>
      {!o.offered_by_landlord ? <Notice tone="info">{t('invest.notOfferedNow')}</Notice> : null}
      {order.map((s, i) => (
        <Row key={s} label={`${i + 1}. ${tk('onboardingStep', s, s)}`} value={i < currentIndex ? t('stepState.done') : i === currentIndex ? t('stepState.current') : t('stepState.upcoming')} />
      ))}
      <Button label={tk('onboardingStep', step, step)} onPress={() => router.push(target[step] ?? '/investing/appropriateness')} disabled={!o.offered_by_landlord} />
      <ListItem icon="pie-chart-outline" title={t('invest.browsePortfolios')} onPress={() => router.push('/investing/portfolios')} />
    </Card>
  );
}

function SummaryCards({ o }: { o: InvestOverview }) {
  const { t, lang } = useI18n();
  const { colors } = useTheme();
  const [range, setRange] = useState<Range>('6M');
  const s = o.summary;
  if (!s) return null;
  const points = o.chart?.[range] ?? [];
  const net = o.chart_net_deposits?.[range] ?? null;
  const positive = s.result.cents >= 0;
  return (
    <>
      <Card>
        <AppText variant="label" muted>
          {t('invest.value')}
        </AppText>
        <AppText variant="moneyLarge" accessibilityLabel={`${t('invest.value')}: ${formatMoney(s.value, lang)}`}>
          {formatMoney(s.value, lang)}
        </AppText>
        <AppText variant="bodyStrong" color={positive ? colors.okText : colors.dangerText}>
          {t('invest.resultLine', { amount: formatSignedMoney(s.result, lang), pct: formatPercent(s.result_pct, lang) })}
        </AppText>
        {o.account?.portfolio_label ? <AppText muted>{t('invest.portfolio', { name: o.account.portfolio_label })}</AppText> : null}
      </Card>
      <Card>
        <SectionTitle>{t('invest.chartTitle')}</SectionTitle>
        <Segmented<Range>
          label={t('invest.chartRange')}
          value={range}
          onChange={setRange}
          options={(['1M', '6M', '1Y', 'max'] as Range[]).map((r) => ({ value: r, label: t(`range.${r}`) }))}
        />
        <LineChart points={points} secondary={net} />
      </Card>
      <Card>
        <SectionTitle>{t('invest.breakdown')}</SectionTitle>
        <Row label={t('invest.invested')} value={formatMoney(s.invested_value, lang)} />
        <Row label={t('invest.cash')} value={formatMoney(s.cash, lang)} hint={t('invest.cashHint', { available: formatMoney(s.available, lang), reserved: formatMoney(s.reserved, lang) })} />
        <Row label={t('invest.netDeposits')} value={formatMoney(s.net_deposits, lang)} />
        <Row label={t('invest.result')} value={formatSignedMoney(s.result, lang)} />
        <Row label={t('invest.feesPaid')} value={formatMoney(s.fees_paid, lang)} hint={t('invest.accruedFee', { amount: formatMoney(s.accrued_fee, lang), rate: formatBps(s.fee_rate_bps, lang) })} />
      </Card>
      <Card>
        <SectionTitle>{t('invest.positions')}</SectionTitle>
        {s.positions.length === 0 ? <AppText muted>{t('invest.noPositions')}</AppText> : null}
        {s.positions.map((p) => (
          <Row key={p.fund} label={p.name} value={formatMoney(p.value, lang)} hint={t('invest.units', { units: lang === 'en' ? p.units : p.units.replace('.', ','), asset: p.asset })} />
        ))}
      </Card>
      {o.costs ? (
        <Card>
          <SectionTitle>{t('costs.yourCosts')}</SectionTitle>
          <Row label={t('costs.service1y')} value={formatMoney(o.costs.service_1y, lang)} />
          <Row label={t('costs.fund1y')} value={formatMoney(o.costs.fund_1y, lang)} />
          <Row label={t('costs.transactions')} value={formatMoney(o.costs.transactions, lang)} />
          <Row label={t('costs.total1y')} value={formatMoney(o.costs.total_1y, lang)} strong hint={t('costs.percentPerYear', { pct: formatPercent(o.costs.percent_per_year, lang) })} />
        </Card>
      ) : null}
      {o.withdrawals.length > 0 ? (
        <Card>
          <SectionTitle>{t('withdraw.recent')}</SectionTitle>
          {o.withdrawals.map((w) => (
            <Row key={w.id} label={`${formatDate(w.day ?? w.created_at, lang)} · ${w.iban_masked}`} value={formatMoney(w.amount, lang)} hint={t(`withdrawalStatus.${w.status}`)} />
          ))}
        </Card>
      ) : null}
      <View style={{ height: space.s }} />
    </>
  );
}

function Actions({ o }: { o: InvestOverview }) {
  const { t } = useI18n();
  const active = o.account?.status === 'active';
  const canBuy = active && o.offered_by_landlord && !o.account?.pending_switch;
  const canSell = active && !!o.summary && o.summary.sellable.cents > 0 && !o.account?.pending_switch;
  const go = (href: Href) => () => router.push(href);
  return (
    <Card>
      <SectionTitle>{t('invest.actions')}</SectionTitle>
      {active ? <ListItem icon="arrow-down-circle-outline" title={t('invest.deposit')} subtitle={t('invest.depositHint')} onPress={go('/investing/deposit-instructions')} /> : null}
      {canBuy ? <ListItem icon="add-circle-outline" title={t('side.buy')} onPress={go({ pathname: '/investing/trade', params: { side: 'buy' } } as unknown as Href)} /> : null}
      {canSell ? <ListItem icon="remove-circle-outline" title={t('side.sell')} onPress={go({ pathname: '/investing/trade', params: { side: 'sell' } } as unknown as Href)} /> : null}
      {canBuy ? <ListItem icon="swap-horizontal-outline" title={t('side.switch')} onPress={go({ pathname: '/investing/trade', params: { side: 'switch' } } as unknown as Href)} /> : null}
      {active ? <ListItem icon="exit-outline" title={t('invest.withdraw')} subtitle={t('invest.withdrawHint')} onPress={go('/investing/withdraw')} /> : null}
      <ListItem icon="list-outline" title={t('orders.title')} onPress={go('/investing/orders')} />
      <ListItem icon="document-text-outline" title={t('statements.title')} onPress={go('/investing/statements')} />
      <ListItem icon="pricetag-outline" title={t('feeChange.title')} onPress={go('/investing/fee-change')} />
      <ListItem icon="pie-chart-outline" title={t('invest.browsePortfolios')} onPress={go('/investing/portfolios')} />
      {!o.offered_by_landlord ? <Notice tone="info">{t('invest.notOfferedNow')}</Notice> : null}
    </Card>
  );
}
