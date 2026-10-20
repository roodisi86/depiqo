/**
 * Where to transfer money to invest (from an account in the tenant's own name, always with the
 * reference). The deposit (borg) is never used for this. In the sandbox a simulated transfer can be
 * made for testing; it moves no real money.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import React, { useState } from 'react';

import { api } from '../../../src/api/instance';
import { useIdempotentMutation } from '../../../src/hooks/mutations';
import { useConfig } from '../../../src/hooks/useConfig';
import { useSensitiveScreen } from '../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatMoney, parseAmountToCents } from '../../../src/lib/money';
import { Button } from '../../../src/ui/Button';
import { CopyRow } from '../../../src/ui/CopyRow';
import { FormError, Notice, NotYetAvailable } from '../../../src/ui/feedback';
import { TextField } from '../../../src/ui/form';
import { InvestGuard, InvestQueryState, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Row, Screen, SectionTitle } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

export default function DepositInstructionsScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('depositInstr.title')}>
      <Instructions />
    </InvestGuard>
  );
}

function Instructions() {
  useSensitiveScreen();
  const { t, lang } = useI18n();
  const config = useConfig();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['invest', 'deposit-instructions'], queryFn: api.investDepositInstructions, retry: false });
  const [amount, setAmount] = useState('');
  const simulate = useIdempotentMutation((cents: number, key: string) => api.sandboxDeposit(cents, key), {
    onSuccess: async () => {
      setAmount('');
      await qc.invalidateQueries({ queryKey: ['invest'] });
    },
  });

  const state = InvestQueryState({ isLoading: q.isLoading, error: q.error, onRetry: () => void q.refetch(), title: t('depositInstr.title') });
  if (state) return state;
  if (!q.data) return null;
  if (isPartnerDown(simulate.error)) return <NotYetAvailable />;
  const d = q.data;
  const cents = parseAmountToCents(amount);
  const sandboxAllowed = d.sandbox && config.data?.sandbox === true && config.data.environment !== 'production';

  return (
    <Screen keyboard>
      <Stack.Screen options={{ title: t('depositInstr.title') }} />
      <AppText>{t('depositInstr.intro')}</AppText>
      <Card>
        <CopyRow label={t('depositInstr.iban')} value={d.iban} mono />
        <Row label={t('depositInstr.beneficiary')} value={d.beneficiary} />
        <CopyRow label={t('depositInstr.reference')} value={d.reference} mono />
      </Card>
      <Notice tone="wait" title={t('depositInstr.noteTitle')}>
        {lang === 'nl' ? d.note : t('depositInstr.note')}
      </Notice>
      {sandboxAllowed ? (
        <Card>
          <SectionTitle>{t('depositInstr.sandboxTitle')}</SectionTitle>
          <Notice tone="wait">{t('depositInstr.sandboxBody')}</Notice>
          <TextField label={t('depositInstr.sandboxAmount')} value={amount} onChangeText={setAmount} keyboardType="decimal-pad" />
          <FormError error={simulate.error} mutation />
          {simulate.data ? <Notice tone="ok">{t('depositInstr.sandboxDone', { value: formatMoney(simulate.data.summary.value, lang) })}</Notice> : null}
          <Button label={t('depositInstr.sandboxSubmit')} variant="secondary" busy={simulate.busy} disabled={!cents || cents <= 0} onPress={() => cents && simulate.submit(cents)} />
        </Card>
      ) : null}
    </Screen>
  );
}
