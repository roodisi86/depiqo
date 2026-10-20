/**
 * Account deletion: what is deleted now, what the law makes us keep, and why it is not possible yet
 * (open deposit, investment money or orders). With the password and an explicit confirmation.
 */
import { useQuery } from '@tanstack/react-query';
import { router, Stack, type Href } from 'expo-router';
import React, { useState } from 'react';
import { Alert, View } from 'react-native';

import { isApiError } from '../../../src/api/errors';
import { api } from '../../../src/api/instance';
import { useAuth } from '../../../src/auth/AuthProvider';
import { useSafeMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { Button } from '../../../src/ui/Button';
import { ErrorState, FormError, Loading, Notice } from '../../../src/ui/feedback';
import { Checkbox, TextField } from '../../../src/ui/form';
import { Card, Screen, SectionTitle } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

export default function DeleteAccount() {
  const { t, tk } = useI18n();
  const auth = useAuth();
  const q = useQuery({ queryKey: ['deletion'], queryFn: api.deletionInfo, staleTime: 0 });
  const [password, setPassword] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const del = useSafeMutation((pw: string) => api.deleteAccount(pw), {
    onSuccess: async () => {
      Alert.alert(t('deleteAccount.doneTitle'), t('deleteAccount.doneBody'));
      // The server revoked every device; forget the session here without calling logout.
      await auth.signOut({ callServer: false, reason: null });
    },
  });

  const title = <Stack.Screen options={{ title: t('deleteAccount.title') }} />;
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) {
    return (
      <Screen>
        {title}
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </Screen>
    );
  }
  const info = q.data;
  const passwordError = isApiError(del.error) && del.error.code === 'invalid_password' ? t('errors.invalid_password') : null;

  return (
    <Screen keyboard>
      {title}
      <AppText>{t('deleteAccount.intro')}</AppText>
      <Card>
        <SectionTitle>{t('deleteAccount.deletedNow')}</SectionTitle>
        {info.deleted_now.map((line) => (
          <AppText key={line}>• {line}</AppText>
        ))}
      </Card>
      <Card>
        <SectionTitle>{t('deleteAccount.keptByLaw')}</SectionTitle>
        {info.kept_by_law.map((line) => (
          <AppText key={line}>• {line}</AppText>
        ))}
      </Card>
      <AppText variant="small" muted>
        {t('common.dutchServerText')}
      </AppText>

      {!info.possible ? (
        <Notice tone="alert" title={t('deleteAccount.notPossible')}>
          <View style={{ gap: 8 }}>
            {info.blockers.map((b, i) => (
              <View key={`${b.code}-${i}`} style={{ gap: 4 }}>
                <AppText variant="bodyStrong">{tk('blocker', b.code, b.message)}</AppText>
                <AppText>{b.message}</AppText>
                <AppText muted>{b.next_step}</AppText>
                {b.deposit_pid ? (
                  <Button label={t('deleteAccount.openDeposit')} variant="ghost" compact onPress={() => router.push(`/deposit/${encodeURIComponent(b.deposit_pid as string)}` as Href)} />
                ) : null}
              </View>
            ))}
          </View>
        </Notice>
      ) : (
        <Card>
          <SectionTitle>{t('deleteAccount.confirmTitle')}</SectionTitle>
          <TextField label={t('deleteAccount.password')} value={password} onChangeText={setPassword} secureTextEntry autoComplete="current-password" error={passwordError} />
          <Checkbox checked={confirmed} onChange={setConfirmed} label={t('deleteAccount.confirmCheckbox')} />
          <FormError error={passwordError ? null : del.error} />
          <Button
            label={t('deleteAccount.button')}
            variant="danger"
            disabled={!confirmed || !password}
            busy={del.busy}
            onPress={() =>
              Alert.alert(t('deleteAccount.alertTitle'), t('deleteAccount.alertBody'), [
                { text: t('common.cancel'), style: 'cancel' },
                { text: t('deleteAccount.button'), style: 'destructive', onPress: () => del.submit(password) },
              ])
            }
          />
        </Card>
      )}
    </Screen>
  );
}
