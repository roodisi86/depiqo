/** Second step: a code from the authenticator app, or a recovery code. */
import { Redirect, router } from 'expo-router';
import React, { useState } from 'react';
import { Alert, StyleSheet, View } from 'react-native';

import { hasCode } from '../../src/api/errors';
import { api } from '../../src/api/instance';
import { useAuth } from '../../src/auth/AuthProvider';
import { clearMfaChallenge, getMfaChallenge } from '../../src/auth/mfaChallenge';
import { useSafeMutation } from '../../src/hooks/mutations';
import { useI18n } from '../../src/i18n/I18nProvider';
import { Button } from '../../src/ui/Button';
import { FormError, Notice } from '../../src/ui/feedback';
import { TextField } from '../../src/ui/form';
import { Screen } from '../../src/ui/layout';
import { AppText } from '../../src/ui/Text';
import { space } from '../../src/ui/theme';

export default function Mfa() {
  const { t } = useI18n();
  const auth = useAuth();
  const challenge = getMfaChallenge();
  const [code, setCode] = useState('');
  const [recovery, setRecovery] = useState(false);
  const [touched, setTouched] = useState(false);

  const verify = useSafeMutation((c: string) => api.loginSecondStep(challenge?.value.mfa_token ?? '', c), {
    onSuccess: async (session) => {
      clearMfaChallenge();
      if (session.second_factor === 'recovery') {
        // A recovery code works once. Tell the user how many are left (set up new ones on the website).
        Alert.alert(t('mfa.recoveryUsedTitle'), t('mfa.recoveryUsedBody', { count: session.recovery_codes_left ?? 0 }));
      }
      await auth.completeLogin(session);
    },
  });

  if (!challenge) return <Redirect href="/login" />;

  const clean = recovery ? code.trim() : code.replace(/\s+/g, '');
  const valid = recovery ? clean.length >= 6 : /^\d{6}$/.test(clean);
  const fatal = hasCode(verify.error, 'mfa_token_invalid') || hasCode(verify.error, 'too_many_attempts');
  const submit = () => {
    setTouched(true);
    if (valid) verify.submit(clean);
  };

  return (
    <Screen edges={['top', 'bottom']} keyboard>
      <View style={styles.head}>
        <AppText variant="title" accessibilityRole="header">
          {t('mfa.title')}
        </AppText>
        <AppText muted>{recovery ? t('mfa.introRecovery') : t('mfa.intro')}</AppText>
      </View>
      <TextField
        label={recovery ? t('mfa.recoveryCode') : t('mfa.code')}
        value={code}
        onChangeText={setCode}
        keyboardType={recovery ? 'default' : 'number-pad'}
        autoCapitalize="none"
        autoComplete={recovery ? 'off' : 'one-time-code'}
        textContentType="oneTimeCode"
        maxLength={recovery ? 40 : 7}
        error={touched && !valid ? (recovery ? t('validation.recoveryCode') : t('validation.code6')) : null}
        onSubmitEditing={submit}
        testID="mfa-code"
      />
      <FormError error={verify.error} />
      {fatal ? (
        <Button
          label={t('mfa.backToLogin')}
          onPress={() => {
            clearMfaChallenge();
            router.replace('/login');
          }}
        />
      ) : (
        <Button label={t('mfa.submit')} onPress={submit} busy={verify.busy} testID="mfa-submit" />
      )}
      <Button
        label={recovery ? t('mfa.useApp') : t('mfa.useRecovery')}
        variant="ghost"
        onPress={() => {
          setRecovery(!recovery);
          setCode('');
          setTouched(false);
        }}
      />
      <Notice tone="info">{t('mfa.lostAccess')}</Notice>
    </Screen>
  );
}

const styles = StyleSheet.create({
  head: { gap: space.s, marginTop: space.xl },
});
