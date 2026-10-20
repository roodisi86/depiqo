/**
 * Model portfolios with costs in euro and example scenarios for an amount the user types.
 * With mode=open: choose one and open the investment account (Idempotency-Key per action).
 * Depiqo gives no advice; the user chooses.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Alert, Pressable, View } from 'react-native';

import { api } from '../../../src/api/instance';
import { useIdempotentMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatBps, formatMoney, parseAmountToCents } from '../../../src/lib/money';
import { Button } from '../../../src/ui/Button';
import { CostsTable, ScenariosTable } from '../../../src/ui/CostsTable';
import { FormError, Notice, NotYetAvailable } from '../../../src/ui/feedback';
import { TextField } from '../../../src/ui/form';
import { InvestGuard, InvestQueryState, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Screen } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';
import { radius, space, useTheme } from '../../../src/ui/theme';

const MIN = 2500;
const MAX = 10_000_000;

export default function PortfoliosScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('portfolios.title')}>
      <Portfolios />
    </InvestGuard>
  );
}

function Portfolios() {
  const { mode } = useLocalSearchParams<{ mode?: string }>();
  const opening = mode === 'open';
  const { t, tk, lang } = useI18n();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const [input, setInput] = useState('1000');
  const [amount, setAmount] = useState(100_000);
  const [chosen, setChosen] = useState<string | null>(null);
  const q = useQuery({ queryKey: ['invest', 'portfolios', amount], queryFn: () => api.portfolios(amount), retry: false });
  const open = useIdempotentMutation((portfolio: string, key: string) => api.openInvestAccount(portfolio, key), {
    onSuccess: async (res) => {
      await qc.invalidateQueries({ queryKey: ['invest'] });
      await qc.invalidateQueries({ queryKey: ['me'] });
      Alert.alert(t('portfolios.openedTitle'), lang === 'nl' ? res.message : t('portfolios.openedBody'));
      router.replace('/invest');
    },
  });

  const state = InvestQueryState({ isLoading: q.isLoading, error: q.error, onRetry: () => void q.refetch(), title: t('portfolios.title') });
  if (state) return state;
  if (!q.data) return null;
  if (isPartnerDown(open.error)) return <NotYetAvailable />;
  const data = q.data;
  const parsed = parseAmountToCents(input);
  const amountError = parsed === null || parsed < MIN || parsed > MAX ? t('validation.amountRange', { min: formatMoney({ cents: MIN, currency: 'EUR' }, lang), max: formatMoney({ cents: MAX, currency: 'EUR' }, lang) }) : null;

  return (
    <Screen keyboard>
      <Stack.Screen options={{ title: opening ? t('portfolios.openTitle') : t('portfolios.title') }} />
      <Notice tone="info">{lang === 'nl' ? data.advice_note : t('portfolios.adviceNote')}</Notice>
      <Card>
        <TextField
          label={t('portfolios.amount')}
          value={input}
          onChangeText={setInput}
          keyboardType="decimal-pad"
          hint={t('portfolios.amountHint')}
          error={amountError}
          onSubmitEditing={() => parsed !== null && !amountError && setAmount(parsed)}
        />
        <Button label={t('portfolios.recalculate')} variant="secondary" disabled={!!amountError} onPress={() => parsed !== null && setAmount(parsed)} />
        <AppText variant="small" muted>
          {t('portfolios.feeRate', { rate: formatBps(data.fee_rate_bps, lang) })}
        </AppText>
      </Card>

      {data.items.map((p) => {
        const selected = chosen === p.code;
        const isCurrent = data.current === p.code;
        return (
          <Pressable
            key={p.code}
            disabled={!opening}
            onPress={() => setChosen(p.code)}
            accessibilityRole={opening ? 'radio' : undefined}
            accessibilityState={opening ? { checked: selected } : undefined}
            accessibilityLabel={`${tk('portfolio', p.code, p.label)}. ${t('portfolios.risk', { risk: p.risk, scale: p.risk_scale })}`}
            style={[{ borderWidth: 2, borderRadius: radius.m, padding: space.l, gap: space.m, backgroundColor: colors.surface, borderColor: selected ? colors.primary : colors.line }]}
          >
            <View style={{ gap: 4 }}>
              <AppText variant="heading">
                {tk('portfolio', p.code, p.label)}
                {isCurrent ? ` · ${t('portfolios.current')}` : ''}
              </AppText>
              <AppText variant="label" color={colors.accentText}>
                {t('portfolios.risk', { risk: p.risk, scale: p.risk_scale })}
              </AppText>
              <AppText>{p.summary}</AppText>
            </View>
            <View style={{ gap: 2 }}>
              {p.funds.map((f) => (
                <AppText key={f.fund} variant="small" muted>
                  {formatBps(f.weight_bps, lang, 0)} {f.name}
                </AppText>
              ))}
            </View>
            <CostsTable costs={p.costs} />
            <ScenariosTable scenarios={p.scenarios} />
          </Pressable>
        );
      })}

      <Notice tone="wait" title={t('invest.riskTitle')}>
        {data.risk_text}
      </Notice>

      {opening ? (
        <>
          <FormError error={open.error} mutation />
          <Button
            label={t('portfolios.openAccount')}
            disabled={!chosen}
            busy={open.busy}
            onPress={() =>
              chosen &&
              Alert.alert(t('portfolios.confirmTitle'), t('portfolios.confirmBody', { name: tk('portfolio', chosen, chosen) }), [
                { text: t('common.cancel'), style: 'cancel' },
                { text: t('portfolios.openAccount'), onPress: () => open.submit(chosen) },
              ])
            }
          />
        </>
      ) : null}
    </Screen>
  );
}
