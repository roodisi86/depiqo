/**
 * Withdraw free money from the investment account to the tenant's own registered account only.
 * Registering an account: with two-step verification and a fresh code it is usable at once, otherwise
 * after a cooling-off period (the server says when). Every withdrawal carries an Idempotency-Key.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { router, Stack } from 'expo-router';
import React, { useState } from 'react';
import { Alert } from 'react-native';

import { api } from '../../../src/api/instance';
import { useIdempotentMutation } from '../../../src/hooks/mutations';
import { useMe } from '../../../src/hooks/useMe';
import { useSensitiveScreen } from '../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatDateTime } from '../../../src/lib/format';
import { formatIban, isValidIban, normalizeIban } from '../../../src/lib/iban';
import { formatMoney, parseAmountToCents } from '../../../src/lib/money';
import { Button } from '../../../src/ui/Button';
import { FormError, Notice, NotYetAvailable } from '../../../src/ui/feedback';
import { TextField } from '../../../src/ui/form';
import { InvestGuard, InvestQueryState, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Row, Screen, SectionTitle } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

export default function WithdrawScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('withdraw.title')}>
      <Withdraw />
    </InvestGuard>
  );
}

function Withdraw() {
  useSensitiveScreen();
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const me = useMe();
  const q = useQuery({ queryKey: ['invest'], queryFn: api.investOverview, retry: false });
  const [iban, setIban] = useState('');
  const [code, setCode] = useState('');
  const [amount, setAmount] = useState('');
  const [replace, setReplace] = useState(false);
  const [touched, setTouched] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const register = useIdempotentMutation(
    (vars: { iban: string; code?: string }, key: string) => api.registerIban(vars.iban, vars.code, key),
    {
      onSuccess: async (res) => {
        setReplace(false);
        setIban('');
        setCode('');
        setMessage(
          res.usable_now ? t('withdraw.ibanUsableNow') : t('withdraw.ibanCoolingOff', { date: formatDateTime(res.usable_from, lang), days: res.cooling_off_days }),
        );
        await qc.invalidateQueries({ queryKey: ['invest'] });
      },
    },
  );
  const withdraw = useIdempotentMutation((cents: number, key: string) => api.withdraw(cents, key), {
    onSuccess: async (res) => {
      setAmount('');
      await qc.invalidateQueries({ queryKey: ['invest'] });
      Alert.alert(t('withdraw.doneTitle'), lang === 'nl' ? res.message : t('withdraw.doneBody'));
      router.replace('/invest');
    },
  });

  const state = InvestQueryState({ isLoading: q.isLoading, error: q.error, onRetry: () => void q.refetch(), title: t('withdraw.title') });
  if (state) return state;
  if (!q.data) return null;
  if (isPartnerDown(register.error) || isPartnerDown(withdraw.error)) return <NotYetAvailable />;

  const acct = q.data.account;
  const available = q.data.summary?.available ?? null;
  const own = acct?.own_iban ?? null;
  const twoFactor = me.data?.two_factor_enabled === true;
  const cents = parseAmountToCents(amount);
  const ibanOk = isValidIban(iban);
  const codeOk = !code || /^\d{6}$/.test(code.trim());
  const amountError = cents === null || cents <= 0 ? t('validation.amount') : available && cents > available.cents ? t('withdraw.tooMuch', { max: formatMoney(available, lang) }) : null;

  const showRegister = !own || replace;

  return (
    <Screen keyboard>
      <Stack.Screen options={{ title: t('withdraw.title') }} />
      <AppText>{t('withdraw.intro')}</AppText>
      {message ? <Notice tone="info">{message}</Notice> : null}

      {own && !replace ? (
        <Card>
          <SectionTitle>{t('withdraw.ownAccount')}</SectionTitle>
          <Row label={t('withdraw.iban')} value={own.masked} />
          {own.registered_at ? <Row label={t('withdraw.registeredAt')} value={formatDateTime(own.registered_at, lang)} /> : null}
          {!own.usable_now ? (
            <Notice tone="wait" title={t('withdraw.coolingOffTitle')}>
              {t('withdraw.coolingOffUntil', { date: formatDateTime(own.usable_from, lang) })}
            </Notice>
          ) : null}
          <Button label={t('withdraw.replaceIban')} variant="ghost" compact onPress={() => setReplace(true)} />
        </Card>
      ) : null}

      {showRegister ? (
        <Card>
          <SectionTitle>{t('withdraw.registerTitle')}</SectionTitle>
          <AppText>{t('withdraw.registerIntro')}</AppText>
          <TextField
            label={t('withdraw.iban')}
            value={iban}
            onChangeText={setIban}
            autoCapitalize="characters"
            autoCorrect={false}
            hint={ibanOk ? formatIban(iban) : t('withdraw.ibanHint')}
            error={touched && !ibanOk ? t('validation.iban') : null}
          />
          {twoFactor ? (
            <TextField
              label={t('withdraw.code')}
              value={code}
              onChangeText={setCode}
              keyboardType="number-pad"
              autoComplete="one-time-code"
              textContentType="oneTimeCode"
              maxLength={6}
              hint={t('withdraw.codeHint')}
              error={touched && !codeOk ? t('validation.code6') : null}
            />
          ) : (
            <Notice tone="info">{t('withdraw.noTwoFactor')}</Notice>
          )}
          <FormError error={register.error} mutation />
          <Button
            label={t('withdraw.register')}
            busy={register.busy}
            onPress={() => {
              setTouched(true);
              if (ibanOk && codeOk) register.submit({ iban: normalizeIban(iban), ...(code.trim() ? { code: code.trim() } : {}) });
            }}
          />
          {replace ? <Button label={t('common.cancel')} variant="ghost" onPress={() => setReplace(false)} /> : null}
        </Card>
      ) : null}

      {own && own.usable_now && !replace ? (
        <Card>
          <SectionTitle>{t('withdraw.amountTitle')}</SectionTitle>
          <Row label={t('withdraw.available')} value={formatMoney(available, lang)} hint={t('withdraw.availableHint')} />
          <TextField label={t('withdraw.amount')} value={amount} onChangeText={setAmount} keyboardType="decimal-pad" error={amount ? amountError : null} />
          {available && available.cents > 0 ? (
            <Button label={t('withdraw.all')} variant="ghost" compact onPress={() => setAmount((available.cents / 100).toFixed(2).replace('.', lang === 'en' ? '.' : ','))} />
          ) : null}
          <FormError error={withdraw.error} mutation />
          <Button
            label={t('withdraw.submit')}
            busy={withdraw.busy}
            disabled={!!amountError}
            onPress={() =>
              cents &&
              Alert.alert(t('withdraw.confirmTitle'), t('withdraw.confirmBody', { amount: formatMoney({ cents, currency: 'EUR' }, lang), iban: own.masked }), [
                { text: t('common.cancel'), style: 'cancel' },
                { text: t('withdraw.submit'), onPress: () => withdraw.submit(cents) },
              ])
            }
          />
        </Card>
      ) : null}
    </Screen>
  );
}
