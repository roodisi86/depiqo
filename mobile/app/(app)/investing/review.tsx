/**
 * Risk acknowledgement before an order. Shows the ex-ante costs in euro, the scenarios, the risk text,
 * that the deposit is separate, and the quote's expiry. The order is placed only after an explicit tick,
 * with an Idempotency-Key that is the same for every retry of this quote.
 */
import { useQueryClient } from '@tanstack/react-query';
import { router, Stack } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Alert } from 'react-native';

import { hasCode } from '../../../src/api/errors';
import { api } from '../../../src/api/instance';
import type { Quote } from '../../../src/api/schemas';
import { useIdempotentMutation } from '../../../src/hooks/mutations';
import { useSensitiveScreen } from '../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatMoney } from '../../../src/lib/money';
import { getQuote, setQuote } from '../../../src/lib/quoteStore';
import { Button } from '../../../src/ui/Button';
import { CostsTable, ScenariosTable } from '../../../src/ui/CostsTable';
import { FormError, Notice, NotYetAvailable } from '../../../src/ui/feedback';
import { Checkbox } from '../../../src/ui/form';
import { InvestGuard, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Row, Screen, SectionTitle } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

export default function ReviewScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('review.title')}>
      <Review />
    </InvestGuard>
  );
}

function secondsLeft(q: Quote | null): number {
  if (!q) return 0;
  return Math.max(0, Math.floor((Date.parse(q.expires_at) - Date.now()) / 1000));
}

function Review() {
  useSensitiveScreen();
  const { t, tk, lang } = useI18n();
  const qc = useQueryClient();
  const [quote] = useState<Quote | null>(() => getQuote());
  const [ack, setAck] = useState(false);
  const [left, setLeft] = useState(() => secondsLeft(quote));

  useEffect(() => {
    const timer = setInterval(() => setLeft(secondsLeft(quote)), 1000);
    return () => clearInterval(timer);
  }, [quote]);

  const order = useIdempotentMutation((quoteId: string, key: string) => api.placeOrder(quoteId, key), {
    onSuccess: async (res) => {
      setQuote(null);
      await qc.invalidateQueries({ queryKey: ['invest'] });
      await qc.invalidateQueries({ queryKey: ['activity'] });
      Alert.alert(t('review.placedTitle'), lang === 'nl' ? res.message : t('review.placedBody'));
      router.replace('/investing/orders');
    },
  });

  if (!quote) {
    return (
      <Screen>
        <Stack.Screen options={{ title: t('review.title') }} />
        <Notice tone="info">{t('review.noQuote')}</Notice>
        <Button label={t('common.back')} onPress={() => router.back()} />
      </Screen>
    );
  }
  if (isPartnerDown(order.error)) return <NotYetAvailable />;

  const expired = left <= 0;
  const stale = hasCode(order.error, 'quote_expired') || hasCode(order.error, 'quote_used') || hasCode(order.error, 'quote_not_found');
  const side = quote.side;
  const mm = Math.floor(left / 60);
  const ss = String(left % 60).padStart(2, '0');

  return (
    <Screen>
      <Stack.Screen options={{ title: t('review.title') }} />
      <AppText variant="title" accessibilityRole="header">
        {tk('side', side, side)}
      </AppText>
      <Card>
        <Row label={t('review.amount')} value={quote.sell_all ? t('review.sellAllValue', { amount: formatMoney(quote.sellable, lang) }) : formatMoney(quote.amount, lang)} strong />
        <Row label={t('review.portfolio')} value={tk('portfolio', quote.portfolio.code, quote.portfolio.label)} hint={t('portfolios.risk', { risk: quote.portfolio.risk, scale: quote.portfolio.risk_scale })} />
        <Row label={t('review.currentValue')} value={formatMoney(quote.current_value, lang)} />
        <Row label={t('trade.available')} value={formatMoney(quote.available, lang)} />
      </Card>

      <Card>
        <CostsTable costs={quote.costs} title={t('review.exAnteCosts')} />
      </Card>
      {quote.scenarios ? (
        <Card>
          <ScenariosTable scenarios={quote.scenarios} />
        </Card>
      ) : null}

      <Notice tone="alert" title={t('invest.riskTitle')}>
        {quote.risk_text}
      </Notice>
      <Card accent>
        <SectionTitle>{t('invest.separationTitle')}</SectionTitle>
        <AppText>{lang === 'nl' ? quote.separation_text : t('invest.separation')}</AppText>
      </Card>
      <AppText variant="small" muted>
        {quote.role_text}
      </AppText>
      <AppText variant="small" muted>
        {lang === 'nl' ? quote.execution_note : t(`review.execution_${side === 'switch' ? 'switch' : 'order'}`)}
      </AppText>
      {lang !== 'nl' ? <AppText variant="small" muted>{t('common.dutchOnly')}</AppText> : null}

      <Notice tone={expired ? 'alert' : 'info'}>{expired ? t('review.expired') : t('review.expiresIn', { time: `${mm}:${ss}` })}</Notice>

      <Checkbox checked={ack} onChange={setAck} disabled={expired} label={t('review.ack')} />
      <FormError error={order.error} mutation />
      {expired || stale ? (
        <Button label={t('review.newQuote')} variant="secondary" onPress={() => router.back()} />
      ) : (
        <Button label={t('review.place', { side: tk('side', side, side) })} disabled={!ack} busy={order.busy} onPress={() => order.submit(quote.quote_id)} />
      )}
      <Button label={t('common.cancel')} variant="ghost" disabled={order.busy} onPress={() => router.back()} />
    </Screen>
  );
}
