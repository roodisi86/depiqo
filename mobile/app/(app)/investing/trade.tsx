/**
 * Buy, sell or switch: the user enters the order, the app asks the server for a quote (costs, scenarios
 * and risk; valid 10 minutes; moves no money) and then shows the risk acknowledgement screen.
 */
import { useQuery } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';

import { api } from '../../../src/api/instance';
import { useSafeMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatMoney, parseAmountToCents } from '../../../src/lib/money';
import { setQuote } from '../../../src/lib/quoteStore';
import { Button } from '../../../src/ui/Button';
import { FormError, NotYetAvailable } from '../../../src/ui/feedback';
import { Checkbox, RadioList, TextField } from '../../../src/ui/form';
import { InvestGuard, InvestQueryState, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Row, Screen } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

type Side = 'buy' | 'sell' | 'switch';

export default function TradeScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('trade.title')}>
      <Trade />
    </InvestGuard>
  );
}

function Trade() {
  const params = useLocalSearchParams<{ side?: string }>();
  const side: Side = params.side === 'sell' || params.side === 'switch' ? params.side : 'buy';
  const { t, tk, lang } = useI18n();
  const overview = useQuery({ queryKey: ['invest'], queryFn: api.investOverview, retry: false });
  const portfolios = useQuery({ queryKey: ['invest', 'portfolios', 100_000], queryFn: () => api.portfolios(100_000), enabled: side === 'switch', retry: false });
  const [amount, setAmount] = useState('');
  const [sellAll, setSellAll] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const quote = useSafeMutation(
    (input: { side: Side; amount_cents?: number; sell_all?: boolean; portfolio?: string }) => api.quote(input),
    {
      onSuccess: (q) => {
        setQuote(q);
        router.push('/investing/review');
      },
    },
  );

  const state = InvestQueryState({ isLoading: overview.isLoading, error: overview.error, onRetry: () => void overview.refetch(), title: t(`trade.title_${side}`) });
  if (state) return state;
  if (!overview.data) return null;
  if (isPartnerDown(quote.error)) return <NotYetAvailable />;
  const o = overview.data;
  const s = o.summary;
  const min = o.minimum_order;
  const cents = parseAmountToCents(amount);
  const amountError =
    side === 'switch' || (side === 'sell' && sellAll) ? null : cents === null ? t('validation.amount') : cents < min.cents ? t('validation.amountMin', { min: formatMoney(min, lang) }) : null;

  const submit = () => {
    setTouched(true);
    if (side === 'switch') {
      if (target) quote.submit({ side, portfolio: target });
      return;
    }
    if (side === 'sell' && sellAll) {
      quote.submit({ side, sell_all: true });
      return;
    }
    if (!amountError && cents !== null) quote.submit({ side, amount_cents: cents });
  };

  return (
    <Screen keyboard>
      <Stack.Screen options={{ title: t(`trade.title_${side}`) }} />
      <AppText>{t(`trade.intro_${side}`)}</AppText>
      {s ? (
        <Card>
          <Row label={t('trade.available')} value={formatMoney(s.available, lang)} />
          <Row label={t('trade.sellable')} value={formatMoney(s.sellable, lang)} />
          {o.account?.portfolio ? <Row label={t('trade.currentPortfolio')} value={tk('portfolio', o.account.portfolio, o.account.portfolio_label)} /> : null}
        </Card>
      ) : null}

      {side === 'switch' ? (
        <Card>
          <RadioList<string>
            label={t('trade.chooseTarget')}
            value={target}
            onChange={setTarget}
            options={(portfolios.data?.items ?? [])
              .filter((p) => p.code !== o.account?.portfolio)
              .map((p) => ({ value: p.code, label: `${tk('portfolio', p.code, p.label)} · ${t('portfolios.risk', { risk: p.risk, scale: p.risk_scale })}` }))}
          />
          {touched && !target ? <AppText variant="small">{t('validation.chooseOne')}</AppText> : null}
          <AppText variant="small" muted>
            {t('trade.switchNote')}
          </AppText>
        </Card>
      ) : (
        <Card>
          {side === 'sell' ? <Checkbox checked={sellAll} onChange={setSellAll} label={t('trade.sellAll')} /> : null}
          {!(side === 'sell' && sellAll) ? (
            <TextField
              label={t('trade.amount')}
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
              hint={t('validation.amountMin', { min: formatMoney(min, lang) })}
              error={touched ? amountError : null}
            />
          ) : null}
        </Card>
      )}
      <FormError error={quote.error} />
      <Button label={t('trade.getQuote')} onPress={submit} busy={quote.busy} />
      <AppText variant="small" muted>
        {t('trade.quoteNote')}
      </AppText>
    </Screen>
  );
}
