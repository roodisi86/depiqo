/**
 * Doorbeleggen: where the tenant's share of the deposit goes after the settlement (own account by
 * default, or the investment account). Only shown when the API offers it. The payout itself is started
 * by the landlord and done by the bank; this only records the choice.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Alert } from 'react-native';

import { isApiError } from '../../../../src/api/errors';
import { api } from '../../../../src/api/instance';
import { useIdempotentMutation } from '../../../../src/hooks/mutations';
import { useInvestGate } from '../../../../src/hooks/useMe';
import { useSensitiveScreen } from '../../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../../src/i18n/I18nProvider';
import { formatDateTime } from '../../../../src/lib/format';
import { formatMoney } from '../../../../src/lib/money';
import { Button } from '../../../../src/ui/Button';
import { ErrorState, FormError, Loading, Notice, NotYetAvailable } from '../../../../src/ui/feedback';
import { Checkbox } from '../../../../src/ui/form';
import { Card, Row, Screen, SectionTitle } from '../../../../src/ui/layout';
import { AppText } from '../../../../src/ui/Text';

export default function PayoutChoiceScreen() {
  useSensitiveScreen();
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const { t, tk, lang } = useI18n();
  const gate = useInvestGate();
  const qc = useQueryClient();
  const [confirmed, setConfirmed] = useState(false);
  const q = useQuery({ queryKey: ['payout-choice', pid], queryFn: () => api.payoutChoice(pid), enabled: gate === 'available', retry: false });
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['payout-choice', pid] });
    await qc.invalidateQueries({ queryKey: ['deposit', pid] });
  };
  const choose = useIdempotentMutation((_: 'invest', key: string) => api.choosePayoutToInvest(pid, key), { onSuccess: refresh });
  const cancel = useIdempotentMutation((_: 'own', key: string) => api.cancelPayoutToInvest(pid, key), { onSuccess: refresh });

  const title = <Stack.Screen options={{ title: t('payoutChoice.title') }} />;
  if (gate !== 'available') {
    return (
      <Screen>
        {title}
        <NotYetAvailable />
      </Screen>
    );
  }
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) {
    return (
      <Screen>
        {title}
        {isApiError(q.error) && q.error.status === 404 ? <Notice tone="info">{t('payoutChoice.notOffered')}</Notice> : <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
      </Screen>
    );
  }
  const p = q.data;
  const toInvest = p.destination === 'invest';
  return (
    <Screen>
      {title}
      <Card>
        <SectionTitle>{t('payoutChoice.current')}</SectionTitle>
        <AppText variant="heading">{toInvest ? t('payoutChoice.toInvest') : t('payoutChoice.toOwn')}</AppText>
        {p.partner ? <Row label={t('payoutChoice.partner')} value={p.partner} /> : null}
        {p.choice ? (
          <>
            <Row label={t('payoutChoice.status')} value={tk('payoutStatus', p.choice.status, p.choice.status)} />
            {p.choice.chosen_at ? <Row label={t('payoutChoice.chosenAt')} value={formatDateTime(p.choice.chosen_at, lang)} /> : null}
            <Row label={t('payoutChoice.paid')} value={formatMoney(p.choice.paid, lang)} hint={p.choice.paid_at ? formatDateTime(p.choice.paid_at, lang) : null} />
          </>
        ) : null}
      </Card>
      <Notice tone="info">{lang === 'nl' ? p.explanation : t('payoutChoice.explanation')}</Notice>
      <Notice tone="wait" title={t('invest.riskTitle')}>
        {p.risk_text}
      </Notice>
      {lang !== 'nl' ? <AppText variant="small" muted>{t('common.dutchOnly')}</AppText> : null}

      {!p.available ? (
        <Notice tone="info">{t('payoutChoice.closed')}</Notice>
      ) : toInvest ? (
        <>
          <FormError error={cancel.error} mutation />
          <Button label={t('payoutChoice.backToOwn')} variant="secondary" busy={cancel.busy} onPress={() => cancel.submit('own')} />
        </>
      ) : (
        <>
          <Checkbox checked={confirmed} onChange={setConfirmed} label={lang === 'nl' ? p.confirmation_text : t('payoutChoice.confirmation')} />
          <FormError error={choose.error} mutation />
          <Button
            label={t('payoutChoice.chooseInvest')}
            disabled={!confirmed}
            busy={choose.busy}
            onPress={() =>
              Alert.alert(t('payoutChoice.confirmTitle'), t('payoutChoice.confirmBody'), [
                { text: t('common.cancel'), style: 'cancel' },
                { text: t('payoutChoice.chooseInvest'), onPress: () => choose.submit('invest') },
              ])
            }
          />
        </>
      )}
    </Screen>
  );
}
